import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.world_improvisation import improvised_world_events, public_world_cause
from eidos.application.world_perception import due_world_observations
from eidos.domain.events import DomainEvent
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
    def test_cause_context_is_physical_not_private(self):
        event = DomainEvent(
            "npc.activity_recorded",
            "pathos",
            {
                "actor_id": "mara",
                "action": "repair",
                "location_id": "workshop",
                "activity": "repair something because I feel lonely",
                "private_thought": "secret",
            },
        )
        self.assertEqual(
            public_world_cause(event, "workshop"),
            {
                "kind": "npc.activity_recorded",
                "location_id": "workshop",
                "actor_id": "mara",
                "action": "repair",
            },
        )

    def test_object_change_without_location_uses_known_resource_location(self):
        class RecordingGateway(FixedGateway):
            async def generate(self, request):
                self.context = json.loads(request.messages[-1].content)
                return await super().generate(request)

        gateway = RecordingGateway('{"no_change": true}')
        cause = DomainEvent(
            "object.condition_changed",
            "pathos",
            {
                "object_id": "shared-tea-service",
                "condition": "repaired",
                "simulated_at": self.now.isoformat(),
                "private_note": "do not share",
            },
        )
        events = asyncio.run(
            improvised_world_events(
                [cause],
                self.now,
                1,
                gateway,
                season="winter",
                weather="Clear",
            )
        )
        self.assertTrue(any(e.kind == "world_event.left_ordinary" for e in events))
        self.assertEqual(
            gateway.context["world_cause"],
            {
                "kind": "object.condition_changed",
                "location_id": "cafe",
                "object_id": "shared-tea-service",
                "condition": "repaired",
            },
        )

    now = datetime(2026, 1, 7, 18, tzinfo=timezone.utc)
    arrival = DomainEvent(
        "pathos.moved",
        "pathos",
        {
            "location_id": "cafe",
            "simulated_at": now.isoformat(),
        },
    )

    def resource(self):
        return DomainEvent(
            "object.registered",
            "pathos",
            {
                "object_id": "shared-tea-service",
                "name": "Shared tea service",
                "owner_id": "mara",
                "custodian_id": "mara",
                "location_id": "cafe",
                "condition": "good",
            },
        )

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
                "participation": "Visitors may ask questions or help annotate a local route.",
                "stakes": "The mapmaker may leave with gaps in the neighborhood record.",
                "affective_tone": -0.25,
                "resource_id": "shared-tea-service",
                "inspiration_signal_id": "none",
                "starts_in_hours": 0,
                "intensity": 0.3,
                "duration_hours": 4,
            }
        )

    def generate_events(self, gateway, history=None, external_signals=None):
        return asyncio.run(
            improvised_world_events(
                [self.arrival, *(history or [])],
                self.now,
                len(history or []) + 1,
                gateway,
                season="winter",
                weather="Clear",
                external_signals=external_signals,
            )
        )

    def test_model_can_propose_a_novel_grounded_event_with_delayed_consequences(self):
        events = self.generate_events(FixedGateway(self.proposal()))
        scheduled = next(event for event in events if event.kind == "world_event.scheduled")
        link = next(event for event in events if event.kind == "world_event.theme_linked")
        resource = next(event for event in events if event.kind == "world_event.resource_linked")
        self.assertEqual(scheduled.payload["event_kind"], "ambient")
        self.assertEqual(scheduled.payload["source"], "causal-world-response")
        self.assertEqual(scheduled.payload["starts_at"], self.now.isoformat())
        self.assertEqual(link.payload["event_type"], "visiting_mapmaker")
        self.assertEqual(link.payload["affective_tone"], -0.25)
        self.assertTrue(link.payload["generated_fiction"])
        self.assertGreater(link.payload["novelty_score"], 0.3)
        self.assertEqual(resource.payload["resource_id"], "shared-tea-service")
        self.assertFalse(any(event.kind == "world_event.occurred" for event in events))
        due = due_world_observations(
            [self.resource(), *events], {"pathos": "cafe"}, self.now + timedelta(hours=2)
        )
        occurred = next(event for event in due if event.kind == "world_event.occurred")
        self.assertEqual(occurred.payload["cause"], "a missed train leaves an open evening")
        memory = next(event for event in due if event.kind == "memory.recorded")
        self.assertEqual(memory.payload["event_type"], "visiting_mapmaker")
        self.assertEqual(memory.payload["affective_tone"], -0.25)

    def test_invalid_output_is_a_recorded_quiet_interval_not_a_scripted_fallback(self):
        events = self.generate_events(FixedGateway("not json"))
        self.assertTrue(any(event.kind == "world_event.generation_requested" for event in events))
        self.assertTrue(any(event.kind == "role.failed" for event in events))
        self.assertFalse(any(event.kind == "world_event.scheduled" for event in events))

    def test_attributed_signal_can_inspire_but_cannot_become_world_fact_directly(self):
        proposal = json.loads(self.proposal())
        proposal["inspiration_signal_id"] = "news-1"
        events = self.generate_events(
            FixedGateway(json.dumps(proposal)),
            external_signals={"news-1": "A real town library announced a repair cafe."},
        )
        linked = next(event for event in events if event.kind == "world_event.signal_linked")
        self.assertEqual(linked.payload["signal_id"], "news-1")
        self.assertFalse(linked.payload["world_fact"])
        self.assertFalse(linked.payload["action_authority"])

        proposal["inspiration_signal_id"] = "made-up-signal"
        rejected = self.generate_events(
            FixedGateway(json.dumps(proposal)),
            external_signals={"news-1": "Attributed inspiration"},
        )
        failure = next(event for event in rejected if event.kind == "role.failed")
        self.assertEqual(failure.payload["error_code"], "unknown_inspiration_signal")
        self.assertEqual(self.generate_events(FixedGateway(self.proposal()), events), [])

    def test_offline_stand_in_exercises_the_same_open_event_contract(self):
        events = self.generate_events(StandInGateway())
        self.assertTrue(any(event.kind == "world_event.accepted" for event in events))
        self.assertTrue(any(event.kind == "world_event.theme_linked" for event in events))

    def test_unknown_or_wrong_place_resource_is_rejected_before_world_scheduling(self):
        proposal = json.loads(self.proposal())
        proposal["resource_id"] = "missing-resource"
        events = self.generate_events(FixedGateway(json.dumps(proposal)))
        failure = next(event for event in events if event.kind == "role.failed")
        self.assertEqual(failure.payload["error_code"], "unknown_resource")
        self.assertFalse(any(event.kind == "world_event.scheduled" for event in events))


if __name__ == "__main__":
    unittest.main()
