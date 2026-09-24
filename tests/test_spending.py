import unittest
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import _standin_money_reply
from eidos.application.economy import financial_consequence_events, financial_foundation_events
from eidos.application.spending import (
    CHRISTMAS_FARE_PENCE,
    PHONE_BILL_PENCE,
    RESERVE_PENCE,
    TIGHT_PENCE,
    money_context,
    spending_events,
    spending_view,
)
from eidos.domain.events import DomainEvent
from eidos.domain.finances import project_finances


def at(month, day, hour):
    return datetime(2026, month, day, hour, tzinfo=timezone.utc)


def spend(history, when, *, location="home", awake=True, balance=100_000):
    return spending_events(history, when, awake=awake, location_id=location, balance_pence=balance)


def gifts(events):
    return [e for e in events if e.payload["category"] == "gifts"]


def occasion(occasion_id, outcome, when):
    return DomainEvent(
        "family.occasion",
        "pathos",
        {
            "occasion_id": occasion_id,
            "person_id": "mum",
            "outcome": outcome,
            "label": "Mum's birthday",
            "simulated_at": when.isoformat(),
            "owner": "pathos",
        },
    )


class SpendingTests(unittest.TestCase):
    def test_weekly_bits_happen_once_on_saturday(self):
        saturday = at(1, 10, 11)
        first = spend([], saturday)
        self.assertEqual([e.payload["category"] for e in first], ["everyday"])
        self.assertTrue(1_600 <= first[0].payload["cost_pence"] <= 3_600)
        self.assertEqual(spend(first, saturday + timedelta(hours=1)), [])
        self.assertEqual(spend([], at(1, 9, 11)), [])
        self.assertEqual(spend([], saturday, awake=False), [])

    def test_phone_bill_is_owed_even_when_money_is_tight(self):
        bill = spend([], at(2, 3, 9), balance=0)
        self.assertEqual([e.payload["category"] for e in bill], ["bills"])
        self.assertEqual(bill[0].payload["cost_pence"], PHONE_BILL_PENCE)

    def test_extras_wait_until_he_can_afford_them(self):
        saturday = at(1, 10, 11)
        self.assertEqual(spend([], saturday, balance=RESERVE_PENCE), [])

    def test_when_money_is_tight_he_keeps_to_the_basics(self):
        saturday = at(1, 10, 11)
        tight = spend([], saturday, balance=TIGHT_PENCE - 1)
        easy = spend([], saturday, balance=100_000)
        self.assertLess(tight[0].payload["cost_pence"], easy[0].payload["cost_pence"])
        self.assertIn("basics", tight[0].payload["text"])

    def test_a_visit_costs_something_at_most_once_a_day(self):
        days = [at(3, day, 20) for day in range(1, 29)]
        spent = [spend([], day, location="crown-anchor") for day in days]
        self.assertGreater(sum(1 for s in spent if s), 20)
        first = next(s for s in spent if s)
        self.assertEqual(first[0].payload["category"], "going_out")
        again = first[0].payload["simulated_at"]
        later = datetime.fromisoformat(again) + timedelta(hours=1)
        self.assertEqual(spend(first, later, location="crown-anchor"), [])
        self.assertEqual(spend([], at(3, 4, 20), location="park"), [])

    def test_no_coffee_on_top_of_a_cafe_meal(self):
        noon = at(3, 4, 12)
        meal = DomainEvent(
            "meal.eaten",
            "pathos",
            {"provision_source": "cafe_service", "simulated_at": noon.isoformat()},
        )
        visits = [spend([meal], noon.replace(day=4, hour=13), location="cafe")]
        self.assertEqual(visits, [[]])

    def test_family_occasions_bring_a_card_and_present_once(self):
        birthday = at(3, 14, 10)
        remembered = occasion("mum-birthday-2026", "remembered", birthday)
        gift = gifts(spend([remembered], birthday))
        self.assertEqual(len(gift), 1)
        self.assertEqual(gifts(spend([remembered, *gift], birthday + timedelta(hours=1))), [])
        slipped = occasion("mum-birthday-2026", "slipped_his_mind", birthday)
        self.assertEqual(gifts(spend([slipped], birthday)), [])
        late = occasion("mum-birthday-2026-late", "forgot", birthday + timedelta(days=1))
        self.assertEqual(
            [e.payload["spend_id"] for e in spend([slipped, late], birthday + timedelta(days=1))],
            ["gift-mum-birthday-2026"],
        )

    def test_christmas_means_a_train_fare_and_presents(self):
        agreed = DomainEvent(
            "family.plan_agreed",
            "pathos",
            {"contact_id": "christmas-2026", "simulated_at": at(12, 6, 19).isoformat()},
        )
        first = spend([agreed], at(12, 6, 20))
        self.assertEqual([e.payload["category"] for e in first], ["travel"])
        self.assertEqual(first[0].payload["cost_pence"], CHRISTMAS_FARE_PENCE)
        presents = spend([agreed, *first], at(12, 12, 14), location="market-hall")
        self.assertIn("gifts", {e.payload["category"] for e in presents})

    def test_the_economy_charges_each_spend_to_the_ledger(self):
        when = at(1, 10, 11)
        account = financial_foundation_events([], when)
        spends = spend(account, when, balance=project_finances(account).balance_pence)
        money = financial_consequence_events([*account, *spends], project_finances(account), when)
        charged = [e for e in money if e.kind == "finance.transaction_recorded"]
        self.assertEqual(len(charged), len(spends))
        self.assertEqual(charged[0].payload["category"], "everyday")
        self.assertEqual(charged[0].causation_id, spends[0].event_id)
        state = project_finances([*account, *spends, *money])
        self.assertLess(state.balance_pence, project_finances(account).balance_pence)
        self.assertEqual(
            spending_view([*account, *spends], when)["everyday"],
            sum(e.payload["cost_pence"] for e in spends),
        )


if __name__ == "__main__":
    unittest.main()


class MoneyTalkTests(unittest.TestCase):
    def test_he_knows_how_money_feels_and_where_it_goes(self):
        when = at(1, 10, 11)
        account = financial_foundation_events([], when)
        spends = spend(account, when)
        money = financial_consequence_events([*account, *spends], project_finances(account), when)
        context = money_context([*account, *spends, *money], when)
        self.assertIn(context["how_it_feels"], {"tight", "careful", "comfortable"})
        self.assertTrue(context["where_it_goes_lately"][0].startswith("bits and bobs"))
        reply = _standin_money_reply(
            "how's money at the moment?", {"identity": {"selfhood": {"money": context}}}
        )
        self.assertIn("bits and bobs", reply)
        self.assertIsNone(_standin_money_reply("how was your day?", {}))
