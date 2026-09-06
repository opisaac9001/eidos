import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.nourishment import nourishment_events
from eidos.domain.state import PathosState


class NourishmentTests(unittest.TestCase):
    noon = datetime(2026, 1, 8, 12, tzinfo=timezone.utc)

    def test_hunger_and_free_time_produce_one_replayable_meal(self):
        state = PathosState(simulated_at=self.noon, awake=True, hunger=0.56, energy=0.5)
        events = nourishment_events([], state, self.noon, pathos_busy=False)
        self.assertEqual([event.kind for event in events], ["meal.eaten"])
        self.assertEqual(events[0].payload["meal_kind"], "lunch")
        after = state.apply(events[0])
        self.assertLess(after.hunger, state.hunger)
        self.assertGreater(after.energy, state.energy)
        self.assertEqual(nourishment_events(events, after, self.noon, pathos_busy=False), [])

    def test_conversation_delays_lunch_within_a_flexible_window(self):
        state = PathosState(simulated_at=self.noon, awake=True, hunger=0.5)
        self.assertEqual(nourishment_events([], state, self.noon, pathos_busy=True), [])
        later = self.noon + timedelta(hours=2)
        events = nourishment_events([], state, later, pathos_busy=False)
        self.assertEqual(events[0].payload["meal_kind"], "lunch")
        self.assertEqual(events[0].payload["simulated_at"], later.isoformat())

    def test_sleep_and_low_hunger_do_not_create_decorative_meals(self):
        sleeping = PathosState(simulated_at=self.noon, awake=False, hunger=0.9)
        self.assertEqual(nourishment_events([], sleeping, self.noon, pathos_busy=False), [])
        full = PathosState(simulated_at=self.noon, awake=True, hunger=0.1)
        self.assertEqual(nourishment_events([], full, self.noon, pathos_busy=False), [])

    def test_pressing_hunger_can_produce_a_bounded_snack_outside_mealtime(self):
        at = self.noon.replace(hour=16)
        state = PathosState(simulated_at=at, awake=True, hunger=0.82, energy=0.3)
        events = nourishment_events([], state, at, pathos_busy=False)
        self.assertEqual(events[0].payload["meal_kind"], "snack")
        after = state.apply(events[0])
        self.assertGreaterEqual(after.hunger, 0.04)
        self.assertLess(after.hunger, state.hunger)


if __name__ == "__main__":
    unittest.main()
