import asyncio
import json
import unittest
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

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
        location = pathos_location_id or "cafe"
        arrival = DomainEvent(
            "pathos.moved",
            "pathos",
            {
                "location_id": location,
                "simulated_at": at.isoformat(),
            },
            event_id=uuid5(NAMESPACE_URL, f"arrival:{at}:{location}"),
        )
        current = [arrival, *(history or [])]
        return asyncio.run(
            expanding_world_events(
                current,
                at,
                len(current),
                gateway,
                pathos_location_id=location,
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

        self.assertEqual(events, [])

    def test_ordinary_arrival_can_remain_ordinary(self):
        at = datetime(2026, 1, 2, 11, tzinfo=timezone.utc)
        events = self.generate(FixedGateway('{"no_change": true}'), at)
        self.assertTrue(any(event.kind == "world.expansion_kept_ordinary" for event in events))
        self.assertFalse(any(event.kind.endswith("_registered") for event in events))
        self.assertEqual(self.generate(FixedGateway(self.candidate()), at, events), [])

    def test_clock_alone_does_not_generate_discoveries(self):
        events = asyncio.run(
            expanding_world_events(
                [],
                datetime(2026, 1, 14, 17, tzinfo=timezone.utc),
                0,
                FixedGateway(self.candidate()),
                pathos_location_id="cafe",
            )
        )
        self.assertEqual(events, [])

    def test_old_future_or_other_location_arrivals_are_not_current_causes(self):
        at = datetime(2026, 1, 2, 11, tzinfo=timezone.utc)
        for timestamp, location in (
            ("2026-01-01T11:00:00+00:00", "cafe"),
            ("2026-01-03T11:00:00+00:00", "cafe"),
            ("2026-01-02T11:00:00+00:00", "park"),
            ("invalid", "cafe"),
        ):
            arrival = DomainEvent(
                "pathos.moved",
                "pathos",
                {
                    "location_id": location,
                    "simulated_at": timestamp,
                },
            )
            events = asyncio.run(
                expanding_world_events(
                    [arrival],
                    at,
                    1,
                    FixedGateway(self.candidate()),
                    pathos_location_id="cafe",
                )
            )
            self.assertEqual(events, [])

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
