import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.wellbeing import physically_adjusted_beat, wellbeing_events
from eidos.domain.events import DomainEvent
from eidos.domain.routine import RoutineBeat
from eidos.domain.state import PathosState
from eidos.domain.wellbeing import WellbeingEpisode, project_wellbeing


class WellbeingTests(unittest.TestCase):
    at = datetime(2026, 1, 10, 8, tzinfo=timezone.utc)

    def started(self, *, severity=0.45, hours=48):
        return DomainEvent(
            "wellbeing.episode_started",
            "pathos",
            {
                "episode_id": "wellbeing:test",
                "condition_kind": "under_the_weather",
                "severity": severity,
                "expected_end_at": (self.at + timedelta(hours=hours)).isoformat(),
                "reason": "Ordinary temporary symptoms.",
                "simulated_at": self.at.isoformat(),
                "clinical_diagnosis": False,
            },
        )

    def test_episode_recovers_monotonically_and_cannot_resolve_early(self):
        start = self.started()
        progress = DomainEvent(
            "wellbeing.episode_progressed",
            "pathos",
            {
                "episode_id": "wellbeing:test",
                "severity": 0.3,
                "simulated_at": (self.at + timedelta(days=1)).isoformat(),
            },
        )
        progressed = project_wellbeing([start, progress]).active
        self.assertIsNotNone(progressed)
        self.assertEqual(progressed.severity, 0.3)  # type: ignore[union-attr]
        early = DomainEvent(
            "wellbeing.episode_resolved",
            "pathos",
            {
                "episode_id": "wellbeing:test",
                "simulated_at": (self.at + timedelta(hours=47)).isoformat(),
            },
        )
        with self.assertRaises(ValueError):
            project_wellbeing([start, progress, early])
        resolved = DomainEvent(
            "wellbeing.episode_resolved",
            "pathos",
            {
                "episode_id": "wellbeing:test",
                "simulated_at": (self.at + timedelta(hours=48)).isoformat(),
            },
        )
        self.assertIsNone(project_wellbeing([start, progress, resolved]).active)

    def test_episode_is_nonclinical_bounded_and_cannot_overlap(self):
        start = self.started()
        with self.assertRaises(ValueError):
            project_wellbeing([start, self.started()])
        diagnosed = DomainEvent(
            "wellbeing.episode_started",
            "pathos",
            {**dict(start.payload), "episode_id": "diagnosed", "clinical_diagnosis": True},
        )
        with self.assertRaises(ValueError):
            project_wellbeing([diagnosed])

    def test_rare_generation_is_replay_stable_and_resolves_on_schedule(self):
        at = datetime(2026, 1, 22, 8, tzinfo=timezone.utc)
        state = PathosState(simulated_at=at, awake=True)
        started = wellbeing_events([], state, at)
        self.assertEqual([event.kind for event in started], ["wellbeing.episode_started"])
        self.assertFalse(started[0].payload["clinical_diagnosis"])
        self.assertEqual(wellbeing_events(started, state, at), [])
        expected = datetime.fromisoformat(str(started[0].payload["expected_end_at"]))
        resolved = wellbeing_events(started, state, expected)
        self.assertEqual([event.kind for event in resolved], ["wellbeing.episode_resolved"])

    def test_physical_capacity_bends_optional_and_severe_planned_time(self):
        optional = RoutineBeat(13, "park", "Walk in the park.", 0.65, "walk")
        moderate = WellbeingEpisode(
            "moderate",
            "headache",
            0.35,
            self.at.isoformat(),
            (self.at + timedelta(days=1)).isoformat(),
            "Temporary",
        )
        adjusted, reason = physically_adjusted_beat(
            optional, moderate, planned=False, protected=False
        )
        self.assertEqual((adjusted.location_id, adjusted.activity), ("home", "physical_recovery"))
        self.assertIn("headache", str(reason))
        work = RoutineBeat(10, "workshop", "Work.", 0.7, "work")
        self.assertEqual(
            physically_adjusted_beat(work, moderate, planned=False, protected=False),
            (work, None),
        )
        severe = WellbeingEpisode(
            "severe",
            "under_the_weather",
            0.55,
            self.at.isoformat(),
            (self.at + timedelta(days=2)).isoformat(),
            "Temporary",
        )
        stopped, _ = physically_adjusted_beat(work, severe, planned=True, protected=False)
        self.assertEqual(stopped.location_id, "home")
        self.assertEqual(
            physically_adjusted_beat(work, severe, planned=True, protected=True),
            (work, None),
        )


if __name__ == "__main__":
    unittest.main()
