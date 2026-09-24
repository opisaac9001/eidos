"""His body over time: knocks at the bench, hangovers, fitness and the dentist."""

from datetime import date, datetime, timedelta, timezone

import pytest

from eidos.application.appraisal import appraisal_events
from eidos.application.body import (
    DENTIST,
    DENTIST_DUE_AFTER,
    HANGOVER_REST,
    body_context,
    body_costs,
    body_events,
    body_patterns,
    body_state,
)
from eidos.application.economy import financial_foundation_events
from eidos.application.selfhood import selfhood_context
from eidos.application.work_rota import SHIFT_WEEKDAYS
from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState
from eidos.domain.world_catalog import project_world_catalog

OPENED = datetime(2026, 1, 5, 8, tzinfo=timezone.utc)  # a Monday


def moved(place: str, at: datetime) -> DomainEvent:
    return DomainEvent(
        "pathos.moved", "pathos", {"location_id": place, "simulated_at": at.isoformat()}
    )


def walk(origin: str, destination: str, at: datetime, minutes: int = 12) -> list[DomainEvent]:
    arrive = at + timedelta(minutes=minutes)
    return [
        DomainEvent(
            "pathos.travel_started",
            "pathos",
            {
                "origin_id": origin,
                "destination_id": destination,
                "depart_at": at.isoformat(),
                "arrive_at": arrive.isoformat(),
                "simulated_at": at.isoformat(),
            },
        ),
        moved(destination, arrive),
    ]


def outing(day: date, place: str, start_hour: int, hours: float) -> list[DomainEvent]:
    start = datetime(day.year, day.month, day.day, start_hour, tzinfo=timezone.utc)
    there = walk("home", place, start)
    back = walk(place, "home", start + timedelta(minutes=12) + timedelta(hours=hours))
    return [*there, *back]


def step(history, at, *, on_shift=None, rest=0.6, calendar=None):
    output = body_events(
        history,
        at,
        project_world_catalog(history),
        awake=7 <= at.hour <= 23,
        rest=rest,
        on_shift=on_shift,
        status_of=(calendar if calendar is not None else {}).get,
    )
    history += output
    return output


def body(history, kind=None):
    return [
        e for e in history if e.kind == "body.event" and (kind is None or e.payload["kind"] == kind)
    ]


def start() -> list[DomainEvent]:
    return list(financial_foundation_events([], OPENED))


# -- injuries --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def two_years_at_the_bench() -> list[DomainEvent]:
    history = start()
    for hour in range(24 * 730):
        at = OPENED + timedelta(hours=hour)
        shift = at.weekday() in SHIFT_WEEKDAYS and 10 <= at.hour < 16
        step(history, at, on_shift=f"work-rota-{at.date()}" if shift else None)
    return history


def test_knocks_at_the_bench_are_rare_and_only_at_work(two_years_at_the_bench) -> None:
    injuries = body(two_years_at_the_bench, "injury")
    assert 1 <= len(injuries) <= 8  # a few a year at most
    for injury in injuries:
        at = datetime.fromisoformat(injury.payload["simulated_at"])
        assert at.weekday() in SHIFT_WEEKDAYS and 10 <= at.hour < 16
        assert injury.payload["schedule_id"].startswith("work-rota-")
    memories = {
        e.payload["source_event_id"] for e in two_years_at_the_bench if e.kind == "memory.recorded"
    }
    assert all(str(e.event_id) in memories for e in injuries)


def test_a_knock_stays_sore_for_a_few_days_and_costs_a_few_plasters(
    two_years_at_the_bench,
) -> None:
    injury = body(two_years_at_the_bench, "injury")[0]
    at = datetime.fromisoformat(injury.payload["simulated_at"])
    history = two_years_at_the_bench[: two_years_at_the_bench.index(injury) + 1]
    context = body_context(history, at + timedelta(days=1))
    assert context is not None
    assert context["sore_at_the_moment"] == injury.payload["sore"]
    later = body_context(history, at + timedelta(days=injury.payload["sore_days"] + 1)) or {}
    assert "sore_at_the_moment" not in later
    costs = body_costs(history, at + timedelta(hours=2))
    assert len(costs) == 1 and 0 < costs[0][1] < 1_000


def test_a_knock_is_felt() -> None:
    history = start()
    at = OPENED.replace(hour=11)
    injury = DomainEvent(
        "body.event",
        "pathos",
        {
            "kind": "injury",
            "injury": "chisel_cut",
            "sore": "a cut",
            "sore_days": 4,
            "simulated_at": at.isoformat(),
        },
    )
    history.append(injury)
    appraised, _ = appraisal_events(history, PathosState(awake=True, simulated_at=at), at)
    felt = [e for e in appraised if e.kind == "appraisal.recorded"]
    assert felt and felt[0].payload["desirability"] < 0


# -- hangovers -------------------------------------------------------------------------


def nights(kind: str, count: int = 80) -> list[DomainEvent]:
    history = start()
    for night in range(count):
        day = OPENED.date() + timedelta(days=night)
        if kind == "pub":
            history += outing(day, "crown-anchor", 19, 4.5)  # home about half eleven
        elif kind == "cafe":
            history += outing(day, "cafe", 14, 2)
        for hour in range(7, 13):
            morning = datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)
            step(history, morning + timedelta(days=1))
    return history


def test_no_hangover_after_a_quiet_evening() -> None:
    assert body(nights("cafe"), "hangover") == []


def test_a_big_night_at_the_crown_sometimes_means_a_rough_morning() -> None:
    history = nights("pub")
    hangovers = body(history, "hangover")
    assert 10 <= len(hangovers) <= 45
    for hangover in hangovers:
        tired = next(e for e in history if e.causation_id == hangover.event_id)
        assert tired.kind == "needs.changed"
        assert tired.payload["rest"] == pytest.approx(0.6 - HANGOVER_REST)
    days = [datetime.fromisoformat(e.payload["simulated_at"]).date() for e in hangovers]
    assert len(days) == len(set(days))


def test_a_leaving_do_is_the_likeliest_hangover() -> None:
    hungover = 0
    for n in range(20):
        history = start()
        evening = OPENED.date() + timedelta(days=7 * n + 4)
        schedule_id = f"leaving-mara-do-{evening.isoformat()}"
        history.append(
            DomainEvent(
                "friend.life_event",
                "pathos",
                {
                    "person_id": "mara",
                    "kind": "leaving_do_agreed",
                    "schedule_id": schedule_id,
                    "simulated_at": OPENED.isoformat(),
                },
            )
        )
        history += outing(evening, "crown-anchor", 19, 3.5)
        for hour in range(7, 13):
            at = datetime(evening.year, evening.month, evening.day, hour, tzinfo=timezone.utc)
            step(history, at + timedelta(days=1), calendar={schedule_id: "completed"})
        hungover += len(body(history, "hangover"))
    assert hungover >= 8


# -- fitness ---------------------------------------------------------------------------


def weeks(active: bool, count: int, history=None, first=OPENED.date()) -> list[DomainEvent]:
    history = history if history is not None else start()
    for day_number in range(count * 7):
        day = first + timedelta(days=day_number)
        if active:
            history += outing(day, "park", 17, 1.5)
        for hour in range(8, 23):
            step(history, datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc))
    return history


def test_fitness_follows_how_much_he_is_out_walking() -> None:
    history = weeks(True, 12)
    fit = body_state(history)
    assert fit.fitness > 0.7
    fitter = body(history, "fitness")
    assert [e.payload["direction"] for e in fitter] == ["fitter"]
    assert body_context(history, OPENED + timedelta(days=84))["fitness"].startswith("fitter")
    history = weeks(False, 16, history, first=OPENED.date() + timedelta(weeks=12))
    assert body_state(history).fitness < 0.3
    assert [e.payload["direction"] for e in body(history, "fitness")] == ["fitter", "less_fit"]
    assert "Out of breath" in body(history, "fitness")[-1].payload["text"]
    summaries = [e for e in history if e.kind == "body.week"]
    # Not the first week (he only lived part of it), nor the week under way.
    assert len(summaries) == 12 + 16 - 2
    assert summaries[0].payload["outdoor_hours"] == pytest.approx(10.5, abs=0.5)


def test_an_unlived_week_is_not_counted() -> None:
    history = start()
    step(history, OPENED.replace(hour=12))
    assert [e for e in history if e.kind == "body.week"] == []


# -- the dentist -----------------------------------------------------------------------


def dentist_year(
    outcome: str = "completed", days: int = 480
) -> tuple[list[DomainEvent], dict[str, str]]:
    history = start()
    calendar: dict[str, str] = {}
    at = OPENED
    appointments: dict[str, datetime] = {}
    for hour in range(24 * days):
        now = at + timedelta(hours=hour)
        for event in step(history, now, calendar=calendar):
            if event.kind == "schedule.created":
                calendar[event.payload["schedule_id"]] = "scheduled"
                appointments[event.payload["schedule_id"]] = datetime.fromisoformat(
                    event.payload["ends_at"]
                )
        for schedule_id, ends in appointments.items():
            if calendar[schedule_id] == "scheduled" and now >= ends:
                calendar[schedule_id] = outcome
                outcome = "completed"  # he makes the next one
    return history, calendar


@pytest.fixture(scope="module")
def a_year_and_a_bit() -> list[DomainEvent]:
    return dentist_year()[0]


def test_he_keeps_meaning_to_book_the_dentist(a_year_and_a_bit) -> None:
    nag = body(a_year_and_a_bit, "dentist_nag")[0]
    booked = body(a_year_and_a_bit, "dentist_booked")[0]
    nagged_at = datetime.fromisoformat(nag.payload["simulated_at"])
    booked_at = datetime.fromisoformat(booked.payload["simulated_at"])
    assert nagged_at - OPENED >= DENTIST_DUE_AFTER
    assert timedelta(0) < booked_at - nagged_at <= timedelta(days=101)
    between = a_year_and_a_bit[: a_year_and_a_bit.index(nag) + 1]
    assert body_patterns(between) == ["putting off booking the dentist"]
    assert body_patterns(a_year_and_a_bit[: a_year_and_a_bit.index(booked) + 1]) == []


def test_the_booking_is_his_decision(a_year_and_a_bit) -> None:
    booked = body(a_year_and_a_bit, "dentist_booked")[0]
    bookings = [e for e in a_year_and_a_bit if e.kind == "schedule.created"]
    assert bookings
    decisions = {e.event_id for e in body(a_year_and_a_bit, "dentist_booked")}
    assert all(e.causation_id in decisions for e in bookings)
    intention = next(e for e in a_year_and_a_bit if e.kind == "intention.adopted")
    assert intention.causation_id == booked.event_id
    assert a_year_and_a_bit.index(intention) < a_year_and_a_bit.index(bookings[0])
    assert bookings[0].payload["location_id"] == DENTIST
    starts = datetime.fromisoformat(bookings[0].payload["starts_at"])
    assert starts.weekday() not in SHIFT_WEEKDAYS and starts.weekday() < 5
    place = next(e for e in a_year_and_a_bit if e.kind == "world.place_registered")
    assert place.payload["entity_id"] == DENTIST
    assert DENTIST in project_world_catalog(a_year_and_a_bit).places


def test_he_goes_and_it_is_fine_or_a_filling(a_year_and_a_bit) -> None:
    visit = body(a_year_and_a_bit, "dentist_visit")[0]
    assert visit.payload["outcome"] in {"fine", "filling"}
    at = datetime.fromisoformat(visit.payload["simulated_at"])
    history = a_year_and_a_bit[: a_year_and_a_bit.index(visit) + 1]
    (spend_id, cost, _), *_ = [c for c in body_costs(history, at) if c[0].startswith("dentist")]
    assert cost == visit.payload["cost_pence"]
    # Not nagged again for months.
    assert all(
        datetime.fromisoformat(e.payload["simulated_at"]) - at > timedelta(days=200)
        for e in body(a_year_and_a_bit, "dentist_nag")
        if datetime.fromisoformat(e.payload["simulated_at"]) > at
    )


def test_a_missed_appointment_is_booked_again() -> None:
    history, _ = dentist_year(outcome="failed", days=620)
    kinds = [e.payload["kind"] for e in body(history) if e.payload["kind"].startswith("dentist")]
    assert kinds[:4] == ["dentist_nag", "dentist_booked", "dentist_missed", "dentist_booked"]
    assert len({e.payload["schedule_id"] for e in history if e.kind == "schedule.created"}) >= 2
    places = [e for e in history if e.kind == "world.place_registered"]
    assert len(places) == 1


def test_it_shows_in_how_he_understands_himself(a_year_and_a_bit) -> None:
    nag = body(a_year_and_a_bit, "dentist_nag")[0]
    at = datetime.fromisoformat(nag.payload["simulated_at"])
    context = selfhood_context(a_year_and_a_bit[: a_year_and_a_bit.index(nag) + 1], at)
    assert "putting off booking the dentist" in context["patterns_he_would_like_to_change"]
    assert "body" in context
