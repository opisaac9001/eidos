import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.self_concept import self_concept_events
from eidos.domain.events import DomainEvent
from eidos.domain.self_concept import project_self_concepts


class SelfConceptTests(unittest.TestCase):
    start = datetime(2026, 1, 1, 21, tzinfo=timezone.utc)

    def outcome(self, day: int, succeeded: bool = True) -> DomainEvent:
        return DomainEvent(
            "commitment.fulfilled" if succeeded else "commitment.missed",
            "pathos",
            {
                "commitment_id": f"promise-{day}",
                "simulated_at": (self.start + timedelta(days=day)).isoformat(),
            },
        )

    def test_repeated_outcomes_form_a_cautious_autobiographical_view(self):
        history = [self.outcome(0), self.outcome(4), self.outcome(8)]
        at = self.start + timedelta(days=10)

        formed = self_concept_events(history, at)

        self.assertEqual(formed[0].kind, "self_concept.formed")
        state = project_self_concepts([*history, *formed])
        concept = state.concepts["pathos-self-concept:follow_through"]
        self.assertEqual(concept.stance, "dependable")
        self.assertEqual(concept.positive_count, 3)
        self.assertEqual(concept.negative_count, 0)
        self.assertLess(concept.confidence, 1.0)
        self.assertIn("Lately", concept.text)

    def test_one_day_or_one_week_of_evidence_is_not_an_identity_story(self):
        same_day = [self.outcome(0), self.outcome(0), self.outcome(0)]
        short_span = [self.outcome(0), self.outcome(2), self.outcome(6)]

        self.assertEqual(self_concept_events(same_day, self.start + timedelta(days=8)), [])
        self.assertEqual(self_concept_events(short_span, self.start + timedelta(days=8)), [])

    def test_new_contradictory_outcomes_can_revise_the_story_without_rewriting_it(self):
        positive = [self.outcome(0), self.outcome(4), self.outcome(8)]
        formed_at = self.start + timedelta(days=10)
        formed = self_concept_events(positive, formed_at)
        negative = [self.outcome(day, False) for day in (11, 13, 15, 17, 24)]
        history = [*positive, *formed, *negative]

        revised = self_concept_events(history, self.start + timedelta(days=25))

        self.assertEqual(revised[0].kind, "self_concept.revised")
        state = project_self_concepts([*history, *revised])
        concept = state.concepts["pathos-self-concept:follow_through"]
        self.assertEqual(concept.revision, 2)
        self.assertEqual(concept.stance, "uneven")
        self.assertEqual(formed[0].payload["stance"], "dependable")

    def test_revision_waits_for_time_and_new_evidence(self):
        history = [self.outcome(0), self.outcome(4), self.outcome(8)]
        formed_at = self.start + timedelta(days=10)
        formed = self_concept_events(history, formed_at)

        self.assertEqual(self_concept_events([*history, *formed], formed_at), [])
        too_soon = [*history, *formed, self.outcome(11, False)]
        self.assertEqual(self_concept_events(too_soon, self.start + timedelta(days=12)), [])

    def test_forged_interpretation_is_rejected_even_when_sources_are_real(self):
        history = [self.outcome(0), self.outcome(4), self.outcome(8)]
        event = self_concept_events(history, self.start + timedelta(days=10))[0]
        forged = DomainEvent(
            event.kind,
            event.aggregate_id,
            {**event.payload, "stance": "struggling"},
        )

        with self.assertRaisesRegex(ValueError, "derive"):
            project_self_concepts([*history, forged])


if __name__ == "__main__":
    unittest.main()
