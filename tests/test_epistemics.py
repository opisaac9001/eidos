import unittest

from eidos.application.epistemics import pathos_known_person_ids
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


if __name__ == "__main__":
    unittest.main()
