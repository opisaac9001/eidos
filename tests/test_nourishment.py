import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.nourishment import nourishment_events, provision_foundation_events
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.state import PathosState


class NourishmentTests(unittest.TestCase):
    noon = datetime(2026, 1, 8, 12, tzinfo=timezone.utc)

    def provisions(self, quantity=4):
        event = provision_foundation_events([], self.noon)[0]
        if quantity != 12:
            stock = DomainEvent(
                "object.stock_changed",
                "pathos",
                {
                    "object_id": "household-provisions",
                    "from_quantity": 12,
                    "quantity": quantity,
                },
            )
            return [event, stock], project_planning([event, stock])
        return [event], project_planning([event])

    def test_hunger_and_free_time_produce_one_replayable_meal(self):
        state = PathosState(simulated_at=self.noon, awake=True, hunger=0.56, energy=0.5)
        history, planning = self.provisions()
        events = nourishment_events(history, state, self.noon, planning, pathos_busy=False)
        self.assertEqual([event.kind for event in events], ["meal.eaten", "object.stock_changed"])
        self.assertEqual(events[0].payload["meal_kind"], "lunch")
        after = state.apply(events[0])
        self.assertLess(after.hunger, state.hunger)
        self.assertGreater(after.energy, state.energy)
        after_stock = project_planning([*history, *events]).objects["household-provisions"]
        self.assertEqual(after_stock.quantity, 3)
        self.assertEqual(
            nourishment_events([*history, *events], after, self.noon, planning, pathos_busy=False),
            [],
        )

    def test_conversation_delays_lunch_within_a_flexible_window(self):
        state = PathosState(simulated_at=self.noon, awake=True, hunger=0.5)
        history, planning = self.provisions()
        self.assertEqual(
            nourishment_events(history, state, self.noon, planning, pathos_busy=True), []
        )
        later = self.noon + timedelta(hours=2)
        events = nourishment_events(history, state, later, planning, pathos_busy=False)
        self.assertEqual(events[0].payload["meal_kind"], "lunch")
        self.assertEqual(events[0].payload["simulated_at"], later.isoformat())

    def test_sleep_and_low_hunger_do_not_create_decorative_meals(self):
        sleeping = PathosState(simulated_at=self.noon, awake=False, hunger=0.9)
        _, planning = self.provisions()
        self.assertEqual(
            nourishment_events([], sleeping, self.noon, planning, pathos_busy=False), []
        )
        full = PathosState(simulated_at=self.noon, awake=True, hunger=0.1)
        self.assertEqual(nourishment_events([], full, self.noon, planning, pathos_busy=False), [])

    def test_pressing_hunger_can_produce_a_bounded_snack_outside_mealtime(self):
        at = self.noon.replace(hour=16)
        state = PathosState(simulated_at=at, awake=True, hunger=0.82, energy=0.3)
        history, planning = self.provisions()
        events = nourishment_events(history, state, at, planning, pathos_busy=False)
        self.assertEqual(events[0].payload["meal_kind"], "snack")
        after = state.apply(events[0])
        self.assertGreaterEqual(after.hunger, 0.04)
        self.assertLess(after.hunger, state.hunger)

    def test_empty_home_stock_prevents_a_meal_but_cafe_service_is_explicit(self):
        history, empty = self.provisions(0)
        home = PathosState(simulated_at=self.noon, awake=True, hunger=0.7)
        unavailable = nourishment_events(history, home, self.noon, empty, pathos_busy=False)
        self.assertEqual([event.kind for event in unavailable], ["meal.unavailable"])
        cafe = PathosState(simulated_at=self.noon, location_id="cafe", awake=True, hunger=0.7)
        served = nourishment_events(history, cafe, self.noon, empty, pathos_busy=False)
        self.assertEqual([event.kind for event in served], ["meal.eaten"])
        self.assertEqual(served[0].payload["provision_source"], "cafe_service")

    def test_household_provisions_are_seeded_once(self):
        events = provision_foundation_events([], self.noon)
        item = project_planning(events).objects["household-provisions"]
        self.assertEqual((item.quantity, item.reorder_at, item.unit), (12, 3, "meal portions"))
        self.assertEqual(provision_foundation_events(events, self.noon), [])


if __name__ == "__main__":
    unittest.main()
