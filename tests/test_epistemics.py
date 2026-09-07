import unittest
from datetime import datetime, timezone

from eidos.application.epistemics import (
    pathos_known_person_ids,
    pathos_person_introduction_event,
)
from eidos.domain.events import DomainEvent


class EpistemicViewTests(unittest.TestCase):
    def test_catalog_existence_and_npc_private_state_are_not_pathos_knowledge(self):
        history = [
            DomainEvent("world.person_registered", "system", {"person_id": "sana"}),
            DomainEvent(
                "npc.activity_recorded",
                "system",
                {"person_id": "sana", "owner": "sana", "activity": "worked"},
            ),
        ]
        self.assertEqual(pathos_known_person_ids(history), frozenset())

    def test_direct_encounter_and_pathos_memory_materialize_a_known_person(self):
        history = [
            DomainEvent("npc.encountered", "pathos", {"person_id": "mara"}),
            DomainEvent(
                "memory.recorded",
                "pathos",
                {"person_id": "ellis", "owner": "pathos", "text": "Ellis helped."},
            ),
            DomainEvent(
                "memory.recorded",
                "system",
                {"person_id": "rowan", "owner": "rowan", "text": "Private."},
            ),
        ]
        self.assertEqual(pathos_known_person_ids(history), frozenset({"mara", "ellis"}))

    def test_a_sourced_introduction_materializes_a_person_without_repeating(self):
        started = DomainEvent("scene.started", "pathos", {"scene_id": "first-talk"})
        introduced = pathos_person_introduction_event(
            [],
            person_id="sana",
            source_event=started,
            simulated_at=datetime(2026, 1, 14, 10, tzinfo=timezone.utc),
            location_id="cafe",
            manner="in_person_conversation",
        )
        self.assertIsNotNone(introduced)
        assert introduced is not None
        self.assertEqual(introduced.causation_id, started.event_id)
        self.assertEqual(pathos_known_person_ids([introduced]), frozenset({"sana"}))
        self.assertIsNone(
            pathos_person_introduction_event(
                [introduced],
                person_id="sana",
                source_event=started,
                simulated_at=datetime(2026, 1, 14, 10, tzinfo=timezone.utc),
                location_id="cafe",
                manner="in_person_conversation",
            )
        )


if __name__ == "__main__":
    unittest.main()
