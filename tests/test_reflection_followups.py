import unittest
from datetime import datetime, timezone

from eidos.application.reflection_followups import reflection_reconsideration_events
from eidos.domain.events import DomainEvent


class ReflectionFollowupTests(unittest.TestCase):
    now = datetime(2026, 2, 5, 21, tzinfo=timezone.utc)

    def history(self, *, category="experience", desirability=-0.7, aggregate="pathos"):
        source = DomainEvent(
            "commitment.missed",
            aggregate,
            {
                "commitment_id": "help-rowan",
                "simulated_at": self.now.isoformat(),
            },
        )
        appraisal = DomainEvent(
            "appraisal.recorded",
            aggregate,
            {
                "source_event_id": str(source.event_id),
                "source_kind": source.kind,
                "need": "connection",
                "need_delta": -0.08,
                "desirability": desirability,
                "novelty": 0.3,
                "controllability": 0.65,
                "simulated_at": self.now.isoformat(),
            },
            causation_id=source.event_id,
        )
        memory = DomainEvent(
            "memory.recorded",
            aggregate,
            {
                "text": "I missed the time I promised Rowan.",
                "owner": aggregate,
                "category": category,
                "source_event_id": str(source.event_id),
                "simulated_at": self.now.isoformat(),
            },
        )
        reflection = DomainEvent(
            "reflection.recorded",
            aggregate,
            {
                "text": "I need to decide what to do about that.",
                "source_memory_id": str(memory.event_id),
                "simulated_at": self.now.isoformat(),
            },
            causation_id=memory.event_id,
            correlation_id="reflection-night",
        )
        return [source, appraisal, memory], reflection

    def test_appraised_setback_raises_a_sourced_non_authoritative_question(self):
        history, reflection = self.history()

        events = reflection_reconsideration_events(history, reflection, self.now)

        self.assertEqual(len(events), 1)
        raised = events[0]
        self.assertEqual(raised.payload["target_type"], "commitment")
        self.assertEqual(raised.payload["target_id"], "help-rowan")
        self.assertFalse(raised.payload["action_authority"])
        self.assertEqual(raised.causation_id, reflection.event_id)
        self.assertEqual(
            reflection_reconsideration_events([*history, raised], reflection, self.now), []
        )

    def test_neutral_dream_and_other_owner_reflections_cannot_raise_a_plan_question(self):
        for options in (
            {"desirability": -0.1},
            {"category": "dream"},
            {"aggregate": "mara"},
        ):
            history, reflection = self.history(**options)
            self.assertEqual(reflection_reconsideration_events(history, reflection, self.now), [])


if __name__ == "__main__":
    unittest.main()
