import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.outreach import outreach_events
from eidos.domain.events import DomainEvent
from eidos.domain.outreach import project_outreach_config
from eidos.ports.model_gateway import ModelResponse


class PressureGateway:
    model = "pressure-fixture"

    async def generate(self, request):
        return ModelResponse(
            json.dumps({"text": "I've been waiting for you, and I need you to answer."}),
            "pressure-fixture",
            "test",
            "stop",
        )


class OutreachTests(unittest.TestCase):
    now = datetime(2026, 1, 5, 18, tzinfo=timezone.utc)

    def history(self, enabled=True):
        events = [
            DomainEvent(
                "conversation.message",
                "pathos",
                {
                    "speaker": "you",
                    "text": "Hello",
                    "request_id": "hello",
                    "simulated_at": (self.now - timedelta(days=2)).isoformat(),
                },
            ),
            DomainEvent(
                "conversation.message",
                "pathos",
                {
                    "speaker": "pathos",
                    "text": "Hello back",
                    "request_id": "hello",
                    "simulated_at": (self.now - timedelta(days=2)).isoformat(),
                },
            ),
            DomainEvent(
                "memory.recorded",
                "pathos",
                {
                    "owner": "pathos",
                    "text": "Rain made the square's paving stones shine.",
                    "category": "routine",
                    "simulated_at": self.now.isoformat(),
                },
            ),
        ]
        if enabled:
            events.insert(
                0,
                DomainEvent(
                    "outreach.configured",
                    "pathos",
                    {
                        "enabled": True,
                        "quiet_start_hour": 22,
                        "quiet_end_hour": 8,
                        "minimum_interval_hours": 72,
                    },
                ),
            )
        return events

    def run_outreach(self, history, gateway=None, at=None):
        return asyncio.run(
            outreach_events(
                history,
                at or self.now,
                gateway or StandInGateway(),
                pathos_awake=True,
                context={"location": "Willow Square", "memories": []},
            )
        )

    def test_opted_in_existing_relationship_can_receive_grounded_message(self):
        events = self.run_outreach(self.history())
        message = next(event for event in events if event.kind == "conversation.message")
        self.assertEqual(message.payload["channel"], "in_app_outreach")
        self.assertIn("paving stones", message.payload["text"])
        self.assertIsNotNone(message.causation_id)

    def test_default_off_pending_reply_and_rate_limit_all_prevent_outreach(self):
        self.assertEqual(self.run_outreach(self.history(enabled=False)), [])
        pending = self.history()
        pending.append(
            DomainEvent(
                "conversation.message",
                "pathos",
                {
                    "speaker": "you",
                    "text": "Are you there?",
                    "request_id": "pending",
                    "simulated_at": self.now.isoformat(),
                },
            )
        )
        self.assertEqual(self.run_outreach(pending), [])
        first = self.run_outreach(self.history())
        self.assertEqual(
            self.run_outreach([*self.history(), *first], at=self.now + timedelta(days=1)),
            [],
        )

    def test_guilt_or_dependency_output_is_recorded_but_not_delivered(self):
        events = self.run_outreach(self.history(), PressureGateway())
        self.assertTrue(any(event.kind == "outreach.rejected" for event in events))
        self.assertFalse(any(event.kind == "conversation.message" for event in events))

    def test_configuration_replay_rejects_weakened_safety_limits(self):
        event = self.history()[0]
        payload = dict(event.payload)
        payload["minimum_interval_hours"] = 1
        with self.assertRaisesRegex(ValueError, "cannot be changed"):
            project_outreach_config([DomainEvent("outreach.configured", "pathos", payload)])


if __name__ == "__main__":
    unittest.main()
