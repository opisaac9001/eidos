import unittest
from datetime import datetime, timezone

from eidos.application.economy import (
    CAFE_MEAL_PENCE,
    OPENING_BALANCE_PENCE,
    WEEKLY_HOUSING_PENCE,
    financial_consequence_events,
    financial_foundation_events,
)
from eidos.domain.events import DomainEvent
from eidos.domain.finances import project_finances


class FinanceTests(unittest.TestCase):
    monday = datetime(2026, 1, 5, 8, tzinfo=timezone.utc)
    noon = monday.replace(hour=12)

    def account(self, at=None):
        return financial_foundation_events([], at or self.monday)

    def cafe_meal(self, at=None):
        when = at or self.monday
        return DomainEvent(
            "meal.eaten",
            "pathos",
            {
                "provision_source": "cafe_service",
                "simulated_at": when.isoformat(),
            },
            correlation_id="meal",
        )

    def test_cafe_cost_is_source_linked_and_cannot_repeat(self):
        account = self.account(self.noon)
        meal = self.cafe_meal(self.noon)
        state = project_finances(account)
        events = financial_consequence_events([*account, meal], state, self.noon)
        self.assertEqual([event.kind for event in events], ["finance.transaction_recorded"])
        self.assertEqual(events[0].payload["amount_pence"], -CAFE_MEAL_PENCE)
        self.assertEqual(events[0].causation_id, meal.event_id)
        updated = project_finances([*account, meal, *events])
        self.assertEqual(updated.balance_pence, OPENING_BALANCE_PENCE - CAFE_MEAL_PENCE)
        self.assertEqual(
            financial_consequence_events([*account, meal, *events], updated, self.noon), []
        )

    def test_old_experiences_are_not_charged_when_account_is_added_later(self):
        old_meal = self.cafe_meal(self.noon.replace(day=4))
        account = self.account(self.noon)
        history = [old_meal, *account]
        self.assertEqual(
            financial_consequence_events(history, project_finances(history), self.noon), []
        )

    def test_actual_weekday_work_evidence_earns_one_shift_payment(self):
        at = self.monday.replace(hour=17)
        account = self.account(at)
        work = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "source": "authored-routine",
                "location_id": "workshop",
                "simulated_at": at.replace(hour=14).isoformat(),
            },
        )
        events = financial_consequence_events([*account, work], project_finances(account), at)
        self.assertEqual(events[0].payload["category"], "work_income")
        repeated_state = project_finances([*account, work, *events])
        self.assertEqual(
            financial_consequence_events([*account, work, *events], repeated_state, at), []
        )

    def test_housing_is_paid_or_explicitly_missed_without_overdraft(self):
        account = self.account()
        paid = financial_consequence_events(account, project_finances(account), self.monday)
        self.assertEqual(
            [event.kind for event in paid],
            ["finance.obligation_due", "finance.transaction_recorded"],
        )
        self.assertEqual(paid[-1].payload["amount_pence"], -WEEKLY_HOUSING_PENCE)
        poor_account = DomainEvent(
            "finance.account_opened",
            "pathos",
            {
                "currency": "GBP",
                "opening_balance_pence": 500,
                "simulated_at": self.monday.isoformat(),
            },
        )
        missed = financial_consequence_events(
            [poor_account], project_finances([poor_account]), self.monday
        )
        self.assertEqual(
            [event.kind for event in missed],
            ["finance.obligation_due", "finance.payment_missed"],
        )
        self.assertEqual(project_finances([poor_account, *missed]).balance_pence, 500)

    def test_unaffordable_source_cost_becomes_missed_instead_of_crashing_replay(self):
        poor_account = DomainEvent(
            "finance.account_opened",
            "pathos",
            {
                "currency": "GBP",
                "opening_balance_pence": 500,
                "simulated_at": self.noon.isoformat(),
            },
        )
        meal = self.cafe_meal(self.noon)
        events = financial_consequence_events(
            [poor_account, meal], project_finances([poor_account]), self.noon
        )
        self.assertEqual([event.kind for event in events], ["finance.payment_missed"])
        self.assertEqual(project_finances([poor_account, *events]).balance_pence, 500)

    def test_ledger_rejects_overdraft_and_false_balance(self):
        account = self.account()[0]
        source = self.cafe_meal()
        invalid = DomainEvent(
            "finance.transaction_recorded",
            "pathos",
            {
                "transaction_id": "bad",
                "amount_pence": -13_000,
                "balance_pence": 0,
                "category": "cafe_meal",
                "description": "Impossible charge",
                "source_event_id": str(source.event_id),
                "simulated_at": self.monday.isoformat(),
            },
            causation_id=source.event_id,
        )
        with self.assertRaises(ValueError):
            project_finances([account, invalid])

    def test_failed_provision_delivery_refunds_only_a_charge_that_happened(self):
        at = self.noon
        account = self.account(at)
        order = DomainEvent(
            "object.replenishment_ordered",
            "pathos",
            {
                "order_id": "food-order",
                "object_id": "household-provisions",
                "attempt": 1,
            },
            correlation_id="food-order",
        )
        charged = financial_consequence_events([*account, order], project_finances(account), at)
        state = project_finances([*account, order, *charged])
        cancelled = DomainEvent(
            "object.replenishment_cancelled",
            "pathos",
            {"order_id": "food-order", "object_id": "household-provisions"},
            correlation_id="food-order",
        )
        refunded = financial_consequence_events([*account, order, *charged, cancelled], state, at)
        self.assertEqual(refunded[0].payload["category"], "refund")
        self.assertEqual(
            project_finances([*account, *charged, *refunded]).balance_pence, OPENING_BALANCE_PENCE
        )
        self.assertEqual(
            financial_consequence_events([*account, cancelled], project_finances(account), at),
            [],
        )


if __name__ == "__main__":
    unittest.main()
