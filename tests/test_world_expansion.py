import asyncio
import json
import unittest
from datetime import datetime, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.world_expansion import expanding_world_events
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.world_catalog import project_world_catalog
from eidos.ports.model_gateway import ModelResponse


class FixedGateway:
    model = "fixed"

    def __init__(self, content):
        self.content = content

    async def generate(self, request):
        return ModelResponse(self.content, "fixed", "test", "stop")


class WorldExpansionTests(unittest.TestCase):
    def candidate(self, **changes):
        raw = {
            "entity_kind": "person",
            "entity_id": "sana-reed",
            "name": "Sana Reed",
            "description": "A local instrument repairer who has recently moved back to the neighborhood.",
            "location_id": "cafe",
            "purpose": "Instrument repairer",
            "color": "#7896b2",
            "label": "Sana",
            "x": 50,
            "y": 50,
            "opens_hour": 8,
            "closes_hour": 18,
            "travel_minutes": 10,
        }
        raw.update(changes)
        return json.dumps(raw)

    def generate(self, gateway, at, history=None, pathos_location_id=None):
        current = history or []
        return asyncio.run(
            expanding_world_events(
                current,
                at,
                len(current),
                gateway,
                pathos_location_id=pathos_location_id,
            )
        )

    def test_valid_model_proposal_registers_a_new_persistent_person(self):
        at = datetime(2026, 1, 14, 17, tzinfo=timezone.utc)
        events = self.generate(FixedGateway(self.candidate()), at)
        self.assertTrue(any(event.kind == "world.person_registered" for event in events))
        self.assertIn("sana-reed", project_world_catalog(events).people)
        self.assertTrue(any(event.kind == "world.expansion_accepted" for event in events))

    def test_new_person_materializes_where_pathos_meets_them(self):
        at = datetime(2026, 1, 14, 17, tzinfo=timezone.utc)
        events = self.generate(
            FixedGateway(self.candidate(location_id="cafe")),
            at,
            pathos_location_id="park",
        )
        registered = next(event for event in events if event.kind == "world.person_registered")
        materialized = next(
            event for event in events if event.kind == "person.materialized_from_ambient_population"
        )
        encounter = next(event for event in events if event.kind == "npc.encountered")
        memory = next(event for event in events if event.kind == "memory.recorded")
        self.assertEqual(registered.payload["location_id"], "park")
        self.assertEqual(encounter.payload["person_id"], "sana-reed")
        self.assertEqual(materialized.causation_id, registered.event_id)
        self.assertEqual(materialized.payload["location_id"], "park")
        self.assertEqual(encounter.causation_id, materialized.event_id)
        self.assertEqual(memory.causation_id, encounter.event_id)
        self.assertEqual(memory.payload["person_id"], "sana-reed")

    def test_a_new_person_cannot_appear_inside_pathos_private_home(self):
        at = datetime(2026, 1, 14, 17, tzinfo=timezone.utc)

        events = self.generate(
            FixedGateway(self.candidate()),
            at,
            pathos_location_id="home",
        )

        failure = next(event for event in events if event.kind == "role.failed")
        self.assertEqual(failure.payload["error_code"], "private_location")
        self.assertFalse(any(event.kind == "world.person_registered" for event in events))

    def test_invalid_generation_is_audited_without_registering_anything(self):
        at = datetime(2026, 1, 14, 17, tzinfo=timezone.utc)
        events = self.generate(FixedGateway("not json"), at)
        self.assertTrue(any(event.kind == "role.failed" for event in events))
        self.assertFalse(any(event.kind.endswith("_registered") for event in events))
        self.assertEqual(self.generate(FixedGateway(self.candidate()), at, events), [])

    def test_stand_in_expands_all_three_entity_kinds_across_a_month(self):
        history: list[DomainEvent] = []
        for day in (14, 21, 28):
            at = datetime(2026, 1, day, 17, tzinfo=timezone.utc)
            history.extend(self.generate(StandInGateway(), at, history))
        catalog = project_world_catalog(history)
        self.assertIn("nina-vale", catalog.people)
        self.assertIn("old-glasshouse", catalog.places)
        self.assertIn("blue-handcart", project_planning(history).objects)
        self.assertEqual(
            {
                event.payload["entity_kind"]
                for event in history
                if event.kind == "world.expansion_accepted"
            },
            {"person", "place", "object"},
        )


if __name__ == "__main__":
    unittest.main()
