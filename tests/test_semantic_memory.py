import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.life import semantic_expectation_context
from eidos.application.semantic_memory import semantic_expectation_events
from eidos.domain.events import DomainEvent
from eidos.domain.semantic_memory import project_semantic_expectations


class SemanticMemoryTests(unittest.TestCase):
    midnight = datetime(2026, 6, 15, tzinfo=timezone.utc)

    def memory(
        self,
        days_ago: int,
        *,
        person_id: str = "mara",
        location_id: str = "cafe",
        owner: str = "pathos",
        category: str = "encounter",
        confidence: float = 0.8,
    ) -> DomainEvent:
        return DomainEvent(
            "memory.recorded",
            owner,
            {
                "text": f"I crossed paths with {person_id} at {location_id}.",
                "simulated_at": (self.midnight - timedelta(days=days_ago)).isoformat(),
                "owner": owner,
                "category": category,
                "confidence": confidence,
                "person_id": person_id,
                "location_id": location_id,
            },
        )

    def test_three_distinct_lived_days_form_a_source_linked_expectation(self):
        history = [self.memory(9), self.memory(6), self.memory(3)]

        formed = semantic_expectation_events(history, self.midnight)

        self.assertEqual(len(formed), 1)
        self.assertEqual(formed[0].kind, "semantic.expectation_formed")
        state = project_semantic_expectations([*history, *formed])
        expectation = state.expectations["pathos-person-usually-at:mara"]
        self.assertEqual(expectation.object_value, "cafe")
        self.assertEqual(expectation.distinct_days, 3)
        self.assertEqual(
            expectation.source_memory_ids, tuple(str(item.event_id) for item in history)
        )
        self.assertIn("usually at cafe", expectation.text)
        self.assertLess(expectation.confidence, 1.0)

    def test_repeated_memories_on_one_day_do_not_become_a_general_rule(self):
        history = [self.memory(3), self.memory(3), self.memory(3)]

        self.assertEqual(semantic_expectation_events(history, self.midnight), [])

    def test_dreams_and_other_peoples_private_memories_do_not_train_pathos(self):
        history = [
            self.memory(9),
            self.memory(6, category="dream"),
            self.memory(3, owner="mara"),
        ]

        self.assertEqual(semantic_expectation_events(history, self.midnight), [])

    def test_reinforcement_waits_a_week_and_requires_new_source_memories(self):
        original = [self.memory(12), self.memory(9), self.memory(6)]
        formed = semantic_expectation_events(original, self.midnight)
        next_day = self.midnight + timedelta(days=1)
        new_memory = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "I saw Mara at the cafe again.",
                "simulated_at": next_day.isoformat(),
                "owner": "pathos",
                "category": "encounter",
                "confidence": 0.85,
                "person_id": "mara",
                "location_id": "cafe",
            },
        )
        history = [*original, *formed, new_memory]

        self.assertEqual(semantic_expectation_events(history, next_day), [])
        a_week_later = self.midnight + timedelta(days=7)
        reinforced = semantic_expectation_events(history, a_week_later)
        self.assertEqual(reinforced[0].kind, "semantic.expectation_reinforced")
        state = project_semantic_expectations([*history, *reinforced])
        self.assertEqual(state.expectations["pathos-person-usually-at:mara"].revision, 2)

    def test_projector_rejects_an_expectation_that_lies_about_its_sources(self):
        history = [self.memory(9), self.memory(6), self.memory(3)]
        event = semantic_expectation_events(history, self.midnight)[0]
        forged = DomainEvent(
            event.kind,
            event.aggregate_id,
            {**event.payload, "object_value": "park"},
        )

        with self.assertRaisesRegex(ValueError, "does not support"):
            project_semantic_expectations([*history, forged])

    def test_character_context_omits_operator_source_metadata(self):
        history = [self.memory(9), self.memory(6), self.memory(3)]
        formed = semantic_expectation_events(history, self.midnight)

        context = semantic_expectation_context([*history, *formed])

        self.assertEqual(context[0]["epistemic_status"], "subjective_generalization")
        self.assertNotIn("source_memory_ids", context[0])
        self.assertNotIn("distinct_days", context[0])


if __name__ == "__main__":
    unittest.main()
