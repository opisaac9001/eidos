import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.appraisal import sleep_and_need_events
from eidos.application.sleep_schedule import sleep_window_events
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.sleep import project_sleep_windows
from eidos.domain.state import PathosState


class SleepScheduleTests(unittest.TestCase):
    evening = datetime(2026, 1, 4, 20, tzinfo=timezone.utc)

    def test_low_rest_selects_early_recovery_and_replays_once(self):
        state = PathosState(rest=0.25, energy=0.8)
        events = sleep_window_events([], state, self.evening, project_planning([]))
        window = next(iter(project_sleep_windows(events).values()))
        self.assertEqual(window.bed.hour, 22)
        self.assertEqual(window.wake - window.bed, timedelta(hours=9))
        self.assertIn("low reserves", window.reason)
        self.assertEqual(sleep_window_events(events, state, self.evening, project_planning([])), [])

    def test_high_arousal_can_keep_him_up_until_midnight(self):
        state = PathosState(rest=0.6, arousal=0.8)
        event = sleep_window_events([], state, self.evening, project_planning([]))[0]
        window = next(iter(project_sleep_windows([event]).values()))
        self.assertEqual(window.bed, self.evening.replace(hour=0) + timedelta(days=1))
        self.assertIn("keyed-up", window.reason)

    def test_early_appointment_moves_wake_time_but_preserves_five_hours(self):
        schedule = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "early",
                "title": "Meet Mara",
                "starts_at": (self.evening + timedelta(hours=11)).isoformat(),
                "ends_at": (self.evening + timedelta(hours=12)).isoformat(),
                "location_id": "cafe",
                "actor_id": "pathos",
            },
        )
        event = sleep_window_events(
            [schedule], PathosState(rest=0.5), self.evening, project_planning([schedule])
        )[0]
        window = next(iter(project_sleep_windows([event]).values()))
        self.assertEqual(window.wake, self.evening + timedelta(hours=10))
        self.assertGreaterEqual(window.wake - window.bed, timedelta(hours=5))
        self.assertIn("early commitment", window.reason)

    def test_busy_conversation_delays_actual_sleep_without_changing_plan(self):
        selected = sleep_window_events(
            [], PathosState(rest=0.25), self.evening, project_planning([])
        )
        bedtime = self.evening + timedelta(hours=2)
        busy_events, busy = sleep_and_need_events(
            PathosState(awake=True), bedtime, selected, pathos_busy=True
        )
        self.assertNotIn("sleep.started", [event.kind for event in busy_events])
        self.assertTrue(busy.awake)
        later_events, asleep = sleep_and_need_events(busy, bedtime + timedelta(hours=1), selected)
        self.assertEqual(later_events[0].kind, "sleep.started")
        self.assertFalse(asleep.awake)

    def test_invalid_or_duplicate_windows_are_rejected(self):
        good = sleep_window_events([], PathosState(), self.evening, project_planning([]))[0]
        with self.assertRaises(ValueError):
            project_sleep_windows([good, good])
        invalid = DomainEvent(
            "sleep.window_selected",
            "pathos",
            {
                **dict(good.payload),
                "wake_at": (
                    datetime.fromisoformat(str(good.payload["bedtime"])) + timedelta(hours=3)
                ).isoformat(),
            },
        )
        with self.assertRaises(ValueError):
            project_sleep_windows([invalid])

    def test_worlds_without_selected_windows_keep_legacy_fallback(self):
        events, asleep = sleep_and_need_events(
            PathosState(awake=True), datetime(2026, 1, 4, 23, tzinfo=timezone.utc)
        )
        self.assertEqual(events[0].kind, "sleep.started")
        self.assertFalse(asleep.awake)


if __name__ == "__main__":
    unittest.main()
