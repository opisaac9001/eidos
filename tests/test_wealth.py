"""His share options pay out, and money is looked after the way sensible people do it."""

from datetime import datetime, timedelta, timezone

from eidos.application import economy
from eidos.application.wealth import (
    CGT_EXEMPT_PENCE,
    CGT_RATE,
    EMERGENCY_FUND_PENCE,
    FROM_SAVINGS,
    GROSS_PENCE,
    ISA_ALLOWANCE_PENCE,
    ISA_TOP_UP,
    LANDED,
    MONEY_CHECK,
    MONTH,
    NOTICE,
    SORTED,
    TAX_PAID,
    TAX_RETURN,
    TAX_SET_ASIDE,
    TO_SAVINGS,
    accounts,
    comfortable,
    money_in_words,
    tax_year,
    wealth_events,
)
from eidos.domain.events import DomainEvent

OFFER_AT = datetime(2026, 8, 28, 9, tzinfo=timezone.utc)
CGT = round((GROSS_PENCE - CGT_EXEMPT_PENCE) * CGT_RATE)


def offer() -> DomainEvent:
    return DomainEvent("career.offer_received", "pathos", {"simulated_at": OFFER_AT.isoformat()})


def live(history, start, hours, balance=150_000, ledger=()):
    for hour in range(hours):
        at = start + timedelta(hours=hour)
        out = wealth_events(
            history, at, awake=8 <= at.hour <= 22, balance_pence=balance, ledger=ledger
        )
        history += out
        for e in out:
            if e.kind in {FROM_SAVINGS, TO_SAVINGS, TAX_SET_ASIDE}:
                balance += economy._source_consequence(e)[0]
    return history, balance


def settled():
    return live([offer()], OFFER_AT, 24 * 12)


def test_the_email_the_money_then_an_evening_sorting_it_properly() -> None:
    history, balance = settled()
    kinds = [e.kind for e in history]
    assert kinds.index(NOTICE) < kinds.index(LANDED) < kinds.index(SORTED)
    sorted_at = next(e for e in history if e.kind == SORTED)
    assert 19 <= datetime.fromisoformat(sorted_at.payload["simulated_at"]).hour <= 21
    held = accounts(history)
    assert held.tax_pot == CGT == held.tax_owed  # the tax on the shares, put aside
    assert held.isa == ISA_ALLOWANCE_PENCE
    # What's left in savings is the emergency fund, less what went to his current account.
    assert held.savings == EMERGENCY_FUND_PENCE - (balance - 150_000)
    assert held.general == GROSS_PENCE - CGT - ISA_ALLOWANCE_PENCE - EMERGENCY_FUND_PENCE
    assert 250_000 <= balance <= 300_000
    assert comfortable(history)


def test_the_month_interest_the_fund_and_money_moving_both_ways() -> None:
    history, _ = settled()
    history, low = live(history, datetime(2026, 9, 14, 0, tzinfo=timezone.utc), 24, 100_000)
    assert low >= 290_000  # topped up from savings
    history, high = live(history, datetime(2026, 10, 1, 0, tzinfo=timezone.utc), 12, 900_000)
    assert high <= 500_000 + 1  # swept back into savings on the first
    month = next(e for e in history if e.kind == MONTH and e.payload["month"] == "2026-10")
    assert month.payload["savings_interest_pence"] > 0
    assert abs(month.payload["fund_return"]) < 0.05


def test_freelance_money_gets_a_quarter_put_aside() -> None:
    history, balance = settled()
    paid_at = datetime(2026, 9, 15, 14, tzinfo=timezone.utc)
    paid = DomainEvent(
        "freelance.paid",
        "pathos",
        {"job_id": "piece-x", "fee_pence": 54_000, "simulated_at": paid_at.isoformat()},
    )
    history.append(paid)
    history, after = live(history, paid_at, 3, balance)
    aside = [e for e in history if e.kind == TAX_SET_ASIDE]
    assert len(aside) == 1 and aside[0].payload["amount_pence"] == 13_500


def test_the_tax_return_in_late_january_then_the_bill_from_the_pot() -> None:
    history, _ = settled()
    assert tax_year(OFFER_AT.date()) == "2026-27"
    history, _ = live(history, datetime(2028, 1, 1, tzinfo=timezone.utc), 24 * 31)
    filed = next(e for e in history if e.kind == TAX_RETURN)
    paid = next(e for e in history if e.kind == TAX_PAID)
    assert datetime.fromisoformat(filed.payload["simulated_at"]).day >= 12
    assert paid.payload["tax_year"] == "2026-27" and paid.payload["amount_pence"] >= CGT
    assert accounts(history).tax_owed == 0
    # Nothing due the January before, while that tax year was still running.
    early, _ = live(settled()[0], datetime(2027, 1, 1, tzinfo=timezone.utc), 24 * 31)
    assert not any(e.kind in {TAX_RETURN, TAX_PAID} for e in early)


def test_a_new_tax_year_another_isa_allowance() -> None:
    history, _ = settled()
    history, _ = live(history, datetime(2027, 4, 6, 0, tzinfo=timezone.utc), 24)
    assert any(e.kind == ISA_TOP_UP for e in history)
    assert accounts(history).isa >= 2 * ISA_ALLOWANCE_PENCE


def test_the_monthly_look_at_where_it_went() -> None:
    history, _ = settled()
    ledger = [
        ("2026-09-03T10:00:00+00:00", -12_500, "housing"),
        ("2026-09-05T10:00:00+00:00", -2_400, "takeaway"),
        ("2026-09-07T10:00:00+00:00", -1_150, "takeaway"),
        ("2026-09-09T10:00:00+00:00", -600, "cafe_meal"),
        ("2026-09-10T10:00:00+00:00", 54_000, "work_income"),
        ("2026-09-11T10:00:00+00:00", -13_500, "tax_set_aside"),
    ]
    sunday = datetime(2026, 10, 4, 0, tzinfo=timezone.utc)  # the first Sunday
    history, _ = live(history, sunday, 24, ledger=ledger)
    check = next(e for e in history if e.kind == MONEY_CHECK)
    assert check.payload["spent_pence"] == 12_500 + 2_400 + 1_150 + 600
    note = next(
        e for e in history if e.kind == "memory.recorded" and "money look" in e.payload["text"]
    )
    assert "takeaways" in note.payload["text"] and "£540" in note.payload["text"]


def test_he_knows_hes_comfortable_and_is_understated_about_it() -> None:
    history, balance = settled()
    words = money_in_words(history, balance)
    assert words and "Comfortable" in words and "index funds" in words
    assert "put aside for tax" in words
    assert money_in_words([offer()], 100_000) is None
