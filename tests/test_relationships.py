import unittest

from eidos.domain.events import DomainEvent
from eidos.domain.relationships import RelationshipState, project_relationships


class RelationshipProjectionTests(unittest.TestCase):
    def test_encounters_and_evidence_build_bounded_directed_state(self):
        events = [
            DomainEvent("npc.encountered", "pathos", {"person_id": "mara"}),
            DomainEvent(
                "relationship.changed",
                "pathos",
                {
                    "person_id": "mara",
                    "trust_delta": 0.8,
                    "familiarity_delta": 0.1,
                    "tension_delta": 0.2,
                },
            ),
        ]
        relationship = project_relationships(events).for_person("mara")
        self.assertEqual(relationship.encounters, 1)
        self.assertEqual(relationship.trust, 1.0)
        self.assertAlmostEqual(relationship.familiarity, 0.31)
        self.assertEqual(relationship.tension, 0.2)
        self.assertEqual(project_relationships([]).for_person("nina-vale").trust, 0.3)

    def test_materialized_relationships_are_ordered_and_semantically_checked(self):
        state = project_relationships(
            [DomainEvent("npc.encountered", "pathos", {"person_id": "rowan"})]
        )
        materialized = state.materialized_state()
        self.assertEqual(RelationshipState.from_materialized_state(materialized), state)
        corrupted = {"relationships": [{**materialized["relationships"][0], "encounters": -1}]}
        with self.assertRaises(ValueError):
            RelationshipState.from_materialized_state(corrupted)


if __name__ == "__main__":
    unittest.main()
