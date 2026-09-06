import unittest
from datetime import datetime, timezone

from eidos.domain.events import DomainEvent
from eidos.domain.seasons import project_season, season_change_events, season_for


class SeasonTests(unittest.TestCase):
    def test_calendar_seasons_cover_year_boundaries(self):
        expected = {1: "winter", 3: "spring", 6: "summer", 9: "autumn", 12: "winter"}
        for month, season in expected.items():
            with self.subTest(month=month):
                self.assertEqual(season_for(datetime(2026, month, 1, tzinfo=timezone.utc)), season)

    def test_changes_are_replayable_and_emit_only_at_a_boundary(self):
        winter_at = datetime(2026, 1, 1, 1, tzinfo=timezone.utc)
        winter = season_change_events([], winter_at)
        winter_state = project_season(winter)
        self.assertIsNotNone(winter_state)
        assert winter_state is not None
        self.assertEqual(winter_state.name, "winter")
        self.assertEqual(season_change_events(winter, winter_at.replace(day=2)), [])
        spring_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
        spring = season_change_events(winter, spring_at)
        projected = project_season([*winter, *spring])
        self.assertIsNotNone(projected)
        assert projected is not None
        self.assertEqual(
            (projected.name, spring[0].payload["previous_season"]), ("spring", "winter")
        )

    def test_invalid_season_fact_is_rejected_during_replay(self):
        bad = DomainEvent(
            "world.season_changed",
            "pathos",
            {"season": "monsoon", "simulated_at": "2026-01-01T00:00:00+00:00"},
        )
        with self.assertRaises(ValueError):
            project_season([bad])


if __name__ == "__main__":
    unittest.main()
