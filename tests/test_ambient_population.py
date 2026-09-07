import unittest
from datetime import datetime, timezone

from eidos.application.ambient_population import ambient_population
from eidos.domain.world_catalog import seed_world_catalog


class AmbientPopulationTests(unittest.TestCase):
    catalog = seed_world_catalog()

    def test_population_is_replay_stable_anonymous_and_place_specific(self):
        at = datetime(2026, 1, 7, 12, tzinfo=timezone.utc)

        first = ambient_population(self.catalog, at, "Clear")
        second = ambient_population(self.catalog, at, "Clear")

        self.assertEqual(first, second)
        self.assertEqual(first["home"].estimated_people, 0)
        self.assertGreater(first["cafe"].estimated_people, 0)
        self.assertGreater(first["park"].estimated_people, 0)
        self.assertEqual(
            set(first["park"].__dataclass_fields__),
            {"place_id", "estimated_people", "pace", "activity"},
        )

    def test_footfall_changes_with_time_and_weather_without_creating_people(self):
        noon = datetime(2026, 1, 10, 12, tzinfo=timezone.utc)
        night = datetime(2026, 1, 10, 23, tzinfo=timezone.utc)

        clear = ambient_population(self.catalog, noon, "Clear")
        rain = ambient_population(self.catalog, noon, "Light rain")
        closed = ambient_population(self.catalog, night, "Clear")

        self.assertLess(rain["park"].estimated_people, clear["park"].estimated_people)
        self.assertGreater(rain["cafe"].estimated_people, clear["cafe"].estimated_people)
        self.assertEqual(
            {item.estimated_people for item in closed.values()},
            {0},
        )

    def test_naive_time_is_rejected(self):
        with self.assertRaises(ValueError):
            ambient_population(self.catalog, datetime(2026, 1, 7, 12), "Clear")


if __name__ == "__main__":
    unittest.main()
