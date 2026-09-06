import unittest
from datetime import datetime, timezone

from eidos.application.household import (
    household_adjusted_beat,
    household_completion_events,
    household_foundation_events,
    household_load_events,
)
from eidos.domain.events import DomainEvent
from eidos.domain.household import project_household
from eidos.domain.routine import RoutineBeat


class HouseholdTests(unittest.TestCase):
    at = datetime(2026, 1, 10, 7, tzinfo=timezone.utc)

    def test_daily_living_and_home_meals_accumulate_once(self):
        foundation = household_foundation_events([], self.at)
        state = project_household(foundation)
        meal = DomainEvent(
            "meal.eaten",
            "pathos",
            {"location_id": "home", "simulated_at": self.at.isoformat()},
        )
        added = household_load_events([*foundation, meal], state, self.at)
        self.assertEqual(
            [event.payload["task_kind"] for event in added],
            ["laundry", "tidying", "dishes"],
        )
        updated = project_household([*foundation, meal, *added])
        self.assertEqual(household_load_events([*foundation, meal, *added], updated, self.at), [])
        dish_event = added[-1]
        self.assertEqual(dish_event.causation_id, meal.event_id)

    def test_accumulated_work_can_redirect_free_time_and_then_reduce_load(self):
        foundation = household_foundation_events([], self.at)
        state = project_household(foundation)
        events = []
        for day in range(5):
            when = self.at.replace(day=self.at.day + day)
            added = household_load_events([*foundation, *events], state, when)
            events.extend(added)
            state = project_household([*foundation, *events])
        beat = RoutineBeat(14, "park", "Took an unhurried walk.", 0.7, "walk")
        adjusted, reason = household_adjusted_beat(
            beat,
            state,
            protected=False,
            already_completed_today=False,
        )
        self.assertEqual((adjusted.location_id, adjusted.activity), ("home", "household_laundry"))
        self.assertIn("laundry", reason or "")
        completed = household_completion_events(state, adjusted, self.at.replace(hour=14))
        projected = project_household([*foundation, *events, *completed])
        self.assertLess(projected.loads["laundry"], state.loads["laundry"])

    def test_obligations_and_invalid_completion_are_protected(self):
        state = project_household(household_foundation_events([], self.at))
        work = RoutineBeat(10, "workshop", "Worked.", 0.7, "work")
        self.assertEqual(
            household_adjusted_beat(
                work,
                state,
                protected=False,
                already_completed_today=False,
            ),
            (work, None),
        )
        morning_cafe = RoutineBeat(8, "cafe", "Visited the cafe.", 0.7, "morning_cafe")
        loaded = project_household(
            [
                *household_foundation_events([], self.at),
                DomainEvent(
                    "household.load_added",
                    "pathos",
                    {
                        "change_id": "test-load-1",
                        "task_kind": "dishes",
                        "from_load": 0.12,
                        "load": 0.42,
                        "amount": 0.3,
                        "reason": "test",
                        "simulated_at": self.at.isoformat(),
                    },
                ),
                DomainEvent(
                    "household.load_added",
                    "pathos",
                    {
                        "change_id": "test-load-2",
                        "task_kind": "dishes",
                        "from_load": 0.42,
                        "load": 0.72,
                        "amount": 0.3,
                        "reason": "test",
                        "simulated_at": self.at.isoformat(),
                    },
                ),
            ]
        )
        self.assertEqual(
            household_adjusted_beat(
                morning_cafe,
                loaded,
                protected=False,
                already_completed_today=False,
            ),
            (morning_cafe, None),
        )
        invalid = DomainEvent(
            "household.task_completed",
            "pathos",
            {
                "task_id": "bad",
                "task_kind": "dishes",
                "from_load": 0.12,
                "load": 0.0,
                "amount": 0.12,
                "text": "Washed dishes.",
                "location_id": "cafe",
                "simulated_at": self.at.isoformat(),
            },
        )
        with self.assertRaisesRegex(ValueError, "at home"):
            project_household([*household_foundation_events([], self.at), invalid])

    def test_meals_before_household_introduction_are_not_reinterpreted(self):
        old_meal = DomainEvent(
            "meal.eaten",
            "pathos",
            {"location_id": "home", "simulated_at": self.at.isoformat()},
        )
        introduced_at = self.at.replace(hour=10)
        foundation = household_foundation_events([old_meal], introduced_at)
        history = [old_meal, *foundation]
        state = project_household(history)
        self.assertEqual(household_load_events(history, state, introduced_at), [])


if __name__ == "__main__":
    unittest.main()
