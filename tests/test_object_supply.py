import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.object_supply import object_supply_events
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning


class ObjectSupplyTests(unittest.TestCase):
    now = datetime(2026, 1, 20, 16, tzinfo=timezone.utc)

    def registered(self, suffix: str, quantity: int = 2) -> DomainEvent:
        return DomainEvent(
            "object.registered",
            "pathos",
            {
                "object_id": f"tea-{suffix}",
                "name": "Neighborhood tea",
                "owner_id": "pathos",
                "custodian_id": "pathos",
                "location_id": "home",
                "condition": "good",
                "quantity": quantity,
                "reorder_at": 1,
                "unit": "servings",
                "simulated_at": self.now.isoformat(),
            },
        )

    def supply(
        self,
        history: list[DomainEvent],
        at: datetime,
        *,
        location: str = "home",
        curiosity: float = 1.0,
        reliability: float = 1.0,
        available_pence: int | None = None,
    ) -> list[DomainEvent]:
        return object_supply_events(
            history,
            at,
            project_planning(history),
            pathos_awake=True,
            pathos_location_id=location,
            pathos_energy=0.4,
            curiosity=curiosity,
            values={"reliability": reliability},
            available_pence=available_pence,
        )

    def test_pathos_can_use_or_save_a_finite_supply_without_duplicate_daily_choice(self):
        registration, used = self._find_consumption("use", curiosity=1.0)
        final = project_planning([registration, *used])
        self.assertEqual(final.objects[registration.payload["object_id"]].quantity, 1)
        changed = next(event for event in used if event.kind == "object.stock_changed")
        consumed = next(event for event in used if event.kind == "object.consumed")
        self.assertEqual(changed.causation_id, consumed.event_id)
        repeated = self.supply([registration, *used], self.now)
        self.assertFalse(any(event.kind == "object.consumption_decided" for event in repeated))

        _, saved = self._find_consumption("save", curiosity=0.0)
        self.assertEqual([event.kind for event in saved], ["object.consumption_decided"])

    def test_low_stock_can_be_ordered_and_physically_received(self):
        history, events = self._find_replenishment("order", reliability=1.0)
        ordered = next(event for event in events if event.kind == "object.replenishment_ordered")
        combined = [*history, *events]
        due = datetime.fromisoformat(str(ordered.payload["due_at"]))
        received = self.supply(combined, due, location="home")
        self.assertEqual(received[0].kind, "object.replenishment_received")
        final = project_planning([*combined, *received])
        object_id = str(ordered.payload["object_id"])
        self.assertEqual(final.objects[object_id].quantity, 3)

    def test_replenishment_can_be_declined_or_fail_after_two_missed_handoffs(self):
        _, declined = self._find_replenishment("go_without", reliability=0.0)
        self.assertEqual([event.kind for event in declined], ["object.replenishment_decided"])

        history, events = self._find_replenishment("order", reliability=1.0)
        first_order = next(
            event for event in events if event.kind == "object.replenishment_ordered"
        )
        combined = [*history, *events]
        first_due = datetime.fromisoformat(str(first_order.payload["due_at"]))
        missed = self.supply(combined, first_due, location="park")
        self.assertEqual(
            [event.kind for event in missed],
            ["object.replenishment_missed", "object.replenishment_ordered"],
        )
        combined.extend(missed)
        retry = missed[-1]
        second_due = datetime.fromisoformat(str(retry.payload["due_at"]))
        cancelled = self.supply(combined, second_due, location="park")
        self.assertEqual(
            [event.kind for event in cancelled],
            ["object.replenishment_missed", "object.replenishment_cancelled"],
        )

    def test_food_replenishment_requires_money_before_an_order_exists(self):
        registration = DomainEvent(
            "object.registered",
            "pathos",
            {
                "object_id": "household-provisions",
                "name": "Household provisions",
                "owner_id": "pathos",
                "custodian_id": "pathos",
                "location_id": "home",
                "condition": "usable",
                "quantity": 1,
                "reorder_at": 3,
                "unit": "meal portions",
            },
        )
        stock = DomainEvent(
            "object.stock_changed",
            "pathos",
            {"object_id": "household-provisions", "from_quantity": 1, "quantity": 0},
        )
        events = self.supply(
            [registration, stock],
            self.now.replace(hour=9),
            reliability=1.0,
            available_pence=0,
        )
        self.assertEqual([event.kind for event in events], ["object.replenishment_decided"])
        self.assertEqual(events[0].payload["decision"], "go_without")
        self.assertIn("balance", str(events[0].payload["reason"]))

    def _find_consumption(
        self, decision: str, *, curiosity: float
    ) -> tuple[DomainEvent, list[DomainEvent]]:
        for index in range(300):
            registration = self.registered(str(index))
            events = self.supply([registration], self.now, curiosity=curiosity)
            if events and events[0].payload["decision"] == decision:
                return registration, events
        self.fail(f"No deterministic fixture produced {decision}")

    def _find_replenishment(
        self, decision: str, *, reliability: float
    ) -> tuple[list[DomainEvent], list[DomainEvent]]:
        at = self.now.replace(hour=9) + timedelta(days=1)
        for index in range(300):
            registration = self.registered(str(index))
            changed = DomainEvent(
                "object.stock_changed",
                "pathos",
                {
                    "object_id": registration.payload["object_id"],
                    "from_quantity": 2,
                    "quantity": 1,
                    "reason": "test use",
                    "simulated_at": self.now.isoformat(),
                },
            )
            history = [registration, changed]
            events = self.supply(history, at, reliability=reliability)
            if events and events[0].payload["decision"] == decision:
                return history, events
        self.fail(f"No deterministic fixture produced {decision}")


if __name__ == "__main__":
    unittest.main()
