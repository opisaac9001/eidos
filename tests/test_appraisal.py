import unittest
from datetime import datetime, timezone

from eidos.application.appraisal import appraisal_events, sleep_and_need_events
from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState


class AppraisalTests(unittest.TestCase):
    now = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)

    def test_experience_changes_bounded_need_once_with_source_lineage(self):
        source = DomainEvent(
            "npc.encountered",
            "pathos",
            {"person_id": "mara", "simulated_at": self.now.isoformat()},
        )
        state = PathosState()
        events, updated = appraisal_events([source], state, self.now)
        self.assertEqual([event.kind for event in events], ["appraisal.recorded", "needs.changed"])
        self.assertGreater(updated.connection, state.connection)
        self.assertEqual(events[0].causation_id, source.event_id)
        repeated, same = appraisal_events([source, *events], updated, self.now)
        self.assertEqual(repeated, [])
        self.assertEqual(same, updated)

    def test_need_projection_rejects_unbounded_values(self):
        with self.assertRaises(ValueError):
            PathosState().apply(DomainEvent("needs.changed", "pathos", {"rest": 1.1}))

    def test_dream_residue_is_appraised_without_directly_changing_needs(self):
        dream_effect = DomainEvent(
            "dream.effect_applied",
            "pathos",
            {"valence_delta": -0.05, "source_dream_id": "dream"},
        )
        state = PathosState()
        events, updated = appraisal_events([dream_effect], state, self.now)
        self.assertEqual([event.kind for event in events], ["appraisal.recorded"])
        self.assertEqual(updated, state)

    def test_sleep_recovers_rest_while_waking_hours_create_need_pressure(self):
        sleeping = PathosState(rest=0.4)
        night_events, rested = sleep_and_need_events(
            sleeping, datetime(2026, 1, 1, 2, tzinfo=timezone.utc)
        )
        self.assertGreater(rested.rest, sleeping.rest)
        self.assertFalse(rested.awake)
        morning_events, awake = sleep_and_need_events(
            rested, datetime(2026, 1, 1, 7, tzinfo=timezone.utc)
        )
        self.assertEqual(morning_events[0].kind, "sleep.ended")
        self.assertTrue(awake.awake)
        _, pressured = sleep_and_need_events(awake, datetime(2026, 1, 1, 8, tzinfo=timezone.utc))
        self.assertLess(pressured.connection, awake.connection)
        evening_events, asleep = sleep_and_need_events(
            pressured, datetime(2026, 1, 1, 23, tzinfo=timezone.utc)
        )
        self.assertEqual(evening_events[0].kind, "sleep.started")
        self.assertFalse(asleep.awake)


if __name__ == "__main__":
    unittest.main()
