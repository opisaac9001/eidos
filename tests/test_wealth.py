"""His share options pay out: money tracked, not worried about."""

from datetime import datetime, timedelta, timezone

from eidos.application import economy
from eidos.application.wealth import (
    LANDED,
    MOVED,
    NET_PENCE,
    NOTICE,
    SAVED,
    VALUED,
    comfortable,
    invested_pence,
    money_in_words,
    wealth_events,
)
from eidos.domain.events import DomainEvent

OFFER_AT = datetime(2026, 8, 28, 9, tzinfo=timezone.utc)


def offer() -> DomainEvent:
    return DomainEvent("career.offer_received", "pathos", {"simulated_at": OFFER_AT.isoformat()})


def live(history, start, hours, balance=150_000):
    for hour in range(hours):
        at = start + timedelta(hours=hour)
        out = wealth_events(history, at, awake=8 <= at.hour <= 22, balance_pence=balance)
        history += out
        for e in out:
            if e.kind in {MOVED, SAVED}:
                balance += economy._source_consequence(e)[0]
    return history, balance


def test_the_email_then_the_money_then_a_few_thousand_to_hand() -> None:
    history, balance = live([offer()], OFFER_AT, 24 * 12)
    kinds = [e.kind for e in history]
    assert kinds.index(NOTICE) < kinds.index(LANDED)
    notice = next(e for e in history if e.kind == NOTICE)
    landed = next(e for e in history if e.kind == LANDED)
    assert notice.payload["simulated_at"] >= (OFFER_AT + timedelta(days=2)).isoformat()
    assert (
        landed.payload["simulated_at"]
        >= (datetime.fromisoformat(notice.payload["simulated_at"]) + timedelta(days=7)).isoformat()
    )
    # Up to about four thousand in the current account, a thousand a transaction.
    assert 300_000 <= balance <= 400_000
    assert invested_pence(history) == NET_PENCE - (balance - 150_000)
    assert comfortable(history)


def test_markets_move_month_by_month_and_money_moves_both_ways() -> None:
    history, balance = live([offer()], OFFER_AT, 24 * 12)
    # Five months on, with his balance run down, and then with too much in it.
    history, low = live(history, datetime(2026, 9, 7, 0, tzinfo=timezone.utc), 24 * 8, 120_000)
    assert low > 120_000  # topped up on the Monday
    history, high = live(history, datetime(2026, 10, 1, 0, tzinfo=timezone.utc), 12, 950_000)
    assert high <= 700_000 + 100_000 and any(e.kind == SAVED for e in history)
    valued = [e for e in history if e.kind == VALUED]
    assert valued and valued[-1].payload["month"] == "2026-10"
    assert abs(valued[-1].payload["change_pence"]) < 0.05 * NET_PENCE


def test_he_knows_hes_comfortable_and_is_understated_about_it() -> None:
    history, balance = live([offer()], OFFER_AT, 24 * 12)
    words = money_in_words(history, balance)
    assert words and "Comfortable" in words and "index funds" in words
    assert money_in_words([offer()], 100_000) is None


def test_nothing_before_the_offer() -> None:
    assert wealth_events([], OFFER_AT, awake=True, balance_pence=100) == []
