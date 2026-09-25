"""A week away when the workshop shuts in August."""

from datetime import date, datetime, timedelta, timezone

from eidos.application.economy import financial_foundation_events
from eidos.application.holiday import PLACES, holiday_costs, holiday_events
from eidos.application.seasons import summer_shutdown, workshop_closed
from eidos.domain.world_catalog import project_world_catalog

OPENED = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)


def book(balance=200_000, partner=None, friend=None, year=2026):
    history = financial_foundation_events([], OPENED)
    output = []
    for day in range(1, 32):
        at = datetime(year, 5, day, 19, tzinfo=timezone.utc)
        output += holiday_events(
            [*history, *output],
            at,
            project_world_catalog([*history, *output]),
            awake=True,
            location_id="home",
            balance_pence=balance,
            rent_pence=12_500,
            partner=partner,
            friend=friend,
        )
    return [*history, *output]


def test_the_workshop_shuts_for_the_first_full_week_of_august() -> None:
    monday, friday = summer_shutdown(2026)
    assert monday == date(2026, 8, 3) and friday == date(2026, 8, 7)
    assert all(workshop_closed(monday + timedelta(days=n)) for n in range(5))
    assert not workshop_closed(date(2026, 8, 10))


def test_he_books_a_week_away_in_may_for_the_shutdown() -> None:
    history = book()
    booked = [e for e in history if e.kind == "holiday.stage" and e.payload["stage"] == "booked"]
    assert len(booked) == 1
    trip = next(e for e in history if e.kind == "schedule.created")
    assert trip.causation_id == booked[0].event_id
    assert trip.payload["location_id"] in PLACES
    starts = datetime.fromisoformat(trip.payload["starts_at"])
    assert starts.date() == summer_shutdown(2026)[0] - timedelta(days=2)
    assert any(e.kind == "world.place_registered" for e in history)
    at = datetime.fromisoformat(booked[0].payload["simulated_at"])
    assert holiday_costs(history, at)[0][1] == booked[0].payload["cost_pence"]


def test_with_someone_it_costs_less_and_they_come_too() -> None:
    history = book(partner=("townsfolk-12", "Alex Hale"))
    booked = next(e for e in history if e.payload.get("stage") == "booked")
    assert booked.payload["companion_id"] == "townsfolk-12"
    assert "with Alex" in booked.payload["text"]


def test_when_money_is_tight_he_stays_home_and_notices() -> None:
    history = book(balance=30_000)
    stages = [e.payload["stage"] for e in history if e.kind == "holiday.stage"]
    assert stages == ["skipped"]
    assert not any(e.kind == "schedule.created" for e in history)


def test_a_few_moments_from_the_week() -> None:
    history = book()
    trip = next(e for e in history if e.kind == "schedule.created")
    place = trip.payload["location_id"]
    starts = datetime.fromisoformat(trip.payload["starts_at"])
    catalog = project_world_catalog(history)
    moments = []
    for hour in range(24 * 7):
        at = starts + timedelta(hours=hour)
        moments += holiday_events(
            [*history, *moments],
            at,
            catalog,
            awake=True,
            location_id=place,
            balance_pence=0,
            rent_pence=12_500,
            partner=None,
            friend=None,
        )
    kept = [e for e in moments if e.kind == "holiday.stage"]
    assert len(kept) == 3
