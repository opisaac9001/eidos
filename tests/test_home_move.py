"""Moving flat in his second year, alone or with someone."""

from datetime import datetime, timedelta, timezone

from eidos.application.economy import (
    WEEKLY_HOUSING_PENCE,
    financial_foundation_events,
    weekly_housing_pence,
)
from eidos.application.home_move import (
    SHARED_RENT_PENCE,
    SOLO_RENT_PENCE,
    home_context,
    home_move_events,
    move_costs,
)
from eidos.domain.events import DomainEvent

OPENED = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)


def live(days: int, *, balance: int = 150_000, partner=None, start_day: int = 380):
    history: list[DomainEvent] = financial_foundation_events([], OPENED)
    for day in range(start_day, start_day + days):
        at = (OPENED + timedelta(days=day)).replace(hour=19)
        history += home_move_events(
            history,
            at,
            awake=True,
            balance_pence=balance,
            partner=partner,
            helper=("rowan", "Rowan Price"),
        )
    return history


def stages(history) -> list[str]:
    return [e.payload["stage"] for e in history if e.kind == "home.move"]


def test_not_in_the_first_year_and_not_while_money_is_tight() -> None:
    assert stages(live(15, start_day=300)) == []
    assert stages(live(400, balance=40_000)) == []


def test_he_looks_finds_and_moves_with_a_friend_helping() -> None:
    history = live(400)
    assert stages(history)[:4] == ["looking", "found", "day_agreed", "moved"]
    looking, found, agreed, moved = [e for e in history if e.kind == "home.move"][:4]
    found_at = datetime.fromisoformat(found.payload["simulated_at"])
    assert found_at - datetime.fromisoformat(looking.payload["simulated_at"]) >= timedelta(days=21)
    booking = next(e for e in history if e.kind == "schedule.created")
    assert booking.causation_id == agreed.event_id
    assert booking.payload["companion_id"] == "rowan"
    starts = datetime.fromisoformat(booking.payload["starts_at"])
    assert starts.weekday() == 5
    assert datetime.fromisoformat(moved.payload["simulated_at"]).date() == starts.date()
    assert "Rowan helped" in moved.payload["text"]
    assert weekly_housing_pence(history) == SOLO_RENT_PENCE
    assert weekly_housing_pence(history[: history.index(moved)]) == WEEKLY_HOUSING_PENCE
    costs = move_costs(history[: history.index(found) + 1], found_at)
    assert costs[0][1] == 4 * SOLO_RENT_PENCE
    assert home_context(history)["now"] == moved.payload["flat"]
    # And then not again for years.
    assert stages(history).count("moved") == 1


def test_properly_together_means_moving_in_together() -> None:
    since = OPENED + timedelta(days=60)
    history = live(400, partner=("townsfolk-12", "Alex Hale", since))
    moved = next(e for e in history if e.payload.get("stage") == "moved")
    assert moved.payload["partner_id"] == "townsfolk-12"
    assert weekly_housing_pence(history) == SHARED_RENT_PENCE
    assert "together" in moved.payload["text"]
