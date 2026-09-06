import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.world_improvisation import improvised_world_events
from eidos.application.world_perception import due_world_observations
from eidos.ports.model_gateway import ModelResponse


class FixedGateway:
    model = "fixed"

    def __init__(self, content):
        self.content = content

    async def generate(self, request):
        return ModelResponse(
            content=self.content,
            resolved_model="fixed",
            backend="test",
            finish_reason="stop",
        )


class WorldImprovisationTests(unittest.TestCase):
    now = datetime(2026, 1, 7, 18, tzinfo=timezone.utc)

    def proposal(
        self, description="A visiting mapmaker displays a hand-drawn river atlas in the cafe."
    ):
        return json.dumps(
            {
                "event_type": "visiting_mapmaker",
                "description": description,
                "location_id": "cafe",
                "cause": "a missed train leaves an open evening",
                "theme": "curiosity",
                "opportunity": "ask about the maps",
                "starts_in_hours": 2,
                "intensity": 0.3,
                "duration_hours": 4,
            }
        )

    def generate_events(self, gateway, history=None):
        return asyncio.run(
            improvised_world_events(
                history or [],
                self.now,
                len(history or []),
                gateway,
                season="winter",
                weather="Clear",
            )
        )

    def test_model_can_propose_a_novel_grounded_event_with_delayed_consequences(self):
        events = self.generate_events(FixedGateway(self.proposal()))
        scheduled = next(event for event in events if event.kind == "world_event.scheduled")
        link = next(event for event in events if event.kind == "world_event.theme_linked")
        self.assertEqual(scheduled.payload["event_kind"], "ambient")
        self.assertEqual(scheduled.payload["source"], "model-fiction-proposal")
        self.assertEqual(link.payload["event_type"], "visiting_mapmaker")
        self.assertTrue(link.payload["generated_fiction"])
        self.assertFalse(any(event.kind == "world_event.occurred" for event in events))
        due = due_world_observations(events, {"pathos": "cafe"}, self.now + timedelta(hours=2))
        occurred = next(event for event in due if event.kind == "world_event.occurred")
        self.assertEqual(occurred.payload["cause"], "a missed train leaves an open evening")
        memory = next(event for event in due if event.kind == "memory.recorded")
        self.assertEqual(memory.payload["event_type"], "visiting_mapmaker")

    def test_invalid_output_is_a_recorded_quiet_interval_not_a_scripted_fallback(self):
        events = self.generate_events(FixedGateway("not json"))
        self.assertTrue(any(event.kind == "world_event.generation_requested" for event in events))
        self.assertTrue(any(event.kind == "role.failed" for event in events))
        self.assertFalse(any(event.kind == "world_event.scheduled" for event in events))
        self.assertEqual(self.generate_events(FixedGateway(self.proposal()), events), [])

    def test_offline_stand_in_exercises_the_same_open_event_contract(self):
        events = self.generate_events(StandInGateway())
        self.assertTrue(any(event.kind == "world_event.accepted" for event in events))
        self.assertTrue(any(event.kind == "world_event.theme_linked" for event in events))


if __name__ == "__main__":
    unittest.main()
