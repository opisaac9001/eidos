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
                    "source": "user-conversation",
                    "simulated_at": self.now.isoformat(),
                },
            ),
        ]
        events.append(
            DomainEvent(
                "thought.recorded",
                "pathos",
                {
                    "text": "Rain made the square's paving stones shine.",
                    "source_memory_id": str(events[-1].event_id),
                    "simulated_at": self.now.isoformat(),
                },
            )
        )
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

    def test_legacy_config_has_no_fixed_cooldown(self):
        self.assertEqual(project_outreach_config(self.history()).minimum_interval_hours, 0)

    def test_different_thought_can_lead_to_another_message_same_day(self):
        history = self.history()
        first = self.run_outreach(history)
        second_thought = DomainEvent(
            "thought.recorded",
            "pathos",
            {**dict(history[-1].payload), "text": "I wonder what they thought of that rain."},
        )
        second = self.run_outreach(history + first + [second_thought])
        self.assertTrue(any(e.kind == "conversation.message" for e in second))
        self.assertEqual(self.run_outreach(history + first), [])

    def test_pathos_can_keep_thought_private_without_retrying(self):
        class PrivateGateway:
            model = "private-fixture"

            async def generate(self, request):
                return ModelResponse(
                    json.dumps({"text": "[KEEP_PRIVATE]"}), self.model, "test", "stop"
                )

        history = self.history()
        events = self.run_outreach(history, PrivateGateway())
        self.assertTrue(any(e.kind == "outreach.kept_private" for e in events))
        self.assertFalse(any(e.kind == "conversation.message" for e in events))
        self.assertEqual(self.run_outreach(history + events), [])

    def test_quiet_hours_and_stale_thoughts_do_not_send(self):
        self.assertEqual(self.run_outreach(self.history(), at=self.now.replace(hour=23)), [])
        self.assertEqual(self.run_outreach(self.history(), at=self.now + timedelta(hours=1)), [])

    def test_recent_thought_can_send_outside_fixed_six_pm_slot(self):
        self.assertTrue(
            any(
                e.kind == "conversation.message"
                for e in self.run_outreach(self.history(), at=self.now.replace(hour=18, minute=15))
            )
        )
        history = self.history()
        thought = history[-1]
        history[-1] = DomainEvent(
            "thought.recorded",
            "pathos",
            {**dict(thought.payload), "simulated_at": self.now.replace(hour=12).isoformat()},
        )
        self.assertTrue(
            any(
                e.kind == "conversation.message"
                for e in self.run_outreach(history, at=self.now.replace(hour=12))
            )
        )

    def test_unrelated_memory_and_rejected_attempt_are_not_retried(self):
        history = self.history()
        self.assertEqual(
            self.run_outreach([e for e in history if e.kind != "thought.recorded"]), []
        )
        first = self.run_outreach(history, PressureGateway())
        self.assertEqual(self.run_outreach(history + first), [])


if __name__ == "__main__":
    unittest.main()
