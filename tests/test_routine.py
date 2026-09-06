import unittest
from datetime import datetime, timedelta, timezone

from eidos.domain.routine import (
    RoutineBeat,
    beats_between,
    emotionally_adjusted_beat,
    needs_adjusted_beat,
    routine_for_day,
)


class RoutineTests(unittest.TestCase):
    def test_month_has_broad_replayable_daily_texture(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = start + timedelta(days=30)
        first = beats_between(start, end)
        self.assertEqual(first, beats_between(start, end))
        self.assertGreaterEqual(len({beat.description for _, beat in first}), 25)
        self.assertGreaterEqual(len({beat.activity for _, beat in first}), 18)

    def test_weekends_have_a_different_shape_from_workdays(self):
        friday = routine_for_day(datetime(2026, 1, 9).date())
        saturday = routine_for_day(datetime(2026, 1, 10).date())
        self.assertEqual([beat.hour for beat in friday], [beat.hour for beat in saturday])
        self.assertEqual(
            [beat.location_id for beat in friday if beat.hour in {10, 14}], ["workshop", "workshop"]
        )
        self.assertNotEqual(
            [beat.location_id for beat in friday if beat.hour in {10, 14}],
            [beat.location_id for beat in saturday if beat.hour in {10, 14}],
        )

    def test_restart_boundary_does_not_repeat_a_moment(self):
        start = datetime(2026, 1, 5, 8, tzinfo=timezone.utc)
        middle = start + timedelta(hours=8)
        end = start + timedelta(days=1)
        joined = beats_between(start, middle) + beats_between(middle, end)
        self.assertEqual(joined, beats_between(start, end))

    def test_emotion_can_bend_an_optional_plan_but_not_a_work_obligation(self):
        outing = RoutineBeat(13, "park", "Walk in the park.", 0.6, "walk")
        adjusted, reason = emotionally_adjusted_beat(
            outing, initiative=0.2, social_openness=0.2, sustained_low_hours=30
        )
        self.assertEqual((adjusted.location_id, adjusted.activity), ("home", "restorative_pause"))
        self.assertIn("low mood", reason or "")

        work = RoutineBeat(10, "workshop", "Go to work.", 0.7, "work")
        unchanged, reason = emotionally_adjusted_beat(
            work, initiative=0.2, social_openness=0.2, sustained_low_hours=30
        )
        self.assertEqual(unchanged, work)
        self.assertIsNone(reason)

    def test_strongest_need_can_redirect_free_time_but_not_an_obligation(self):
        outing = RoutineBeat(13, "park", "Walk in the park.", 0.6, "walk")
        connected, reason = needs_adjusted_beat(
            outing,
            rest=0.8,
            connection=0.2,
            curiosity=0.7,
            mastery=0.7,
            hunger=0.2,
        )
        self.assertEqual((connected.location_id, connected.activity), ("cafe", "social_presence"))
        self.assertIn("connection", reason or "")
        nourished, reason = needs_adjusted_beat(
            outing,
            rest=0.8,
            connection=0.8,
            curiosity=0.8,
            mastery=0.8,
            hunger=0.85,
        )
        self.assertEqual((nourished.location_id, nourished.activity), ("home", "need_driven_meal"))
        self.assertIn("hunger", reason or "")
        evening = RoutineBeat(18, "park", "Walk home through the park.", 0.45, "evening_walk")
        practiced, reason = needs_adjusted_beat(
            evening,
            rest=0.8,
            connection=0.8,
            curiosity=0.8,
            mastery=0.2,
            hunger=0.2,
        )
        self.assertEqual((practiced.location_id, practiced.activity), ("home", "craft_practice"))
        self.assertIn("mastery", reason or "")
        work = RoutineBeat(10, "workshop", "Go to work.", 0.7, "work")
        self.assertEqual(
            needs_adjusted_beat(
                work,
                rest=0.1,
                connection=0.8,
                curiosity=0.8,
                mastery=0.8,
                hunger=0.1,
            ),
            (work, None),
        )


if __name__ == "__main__":
    unittest.main()
