"""The turning year shapes his days: light, the clocks, bank holidays, anniversaries."""

from datetime import date, datetime, timedelta, timezone

from eidos.application.seasons import (
    bank_holidays,
    clocks_change,
    daylight,
    seasonal_baseline,
    seasonal_events,
    time_of_year,
    workshop_closed,
)
from eidos.application.work_rota import work_rota_events
from eidos.domain.events import DomainEvent
from eidos.domain.identity import identity_established_event
from eidos.domain.planning import PlanningState, project_planning


def at(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)


def test_the_light_changes_through_the_year() -> None:
    winter = daylight(date(2026, 12, 21))
    summer = daylight(date(2026, 6, 21))
    assert 7.5 < winter[1] - winter[0] < 8.5 and winter[1] < 16.5
    assert 16 < summer[1] - summer[0] < 17 and summer[1] > 21
    assert seasonal_baseline(at(date(2026, 12, 15), 18))[0] < 0
    assert seasonal_baseline(at(date(2026, 6, 20), 19))[0] > 0
    assert (
        seasonal_baseline(at(date(2026, 12, 15), 11))[1]
        > seasonal_baseline(at(date(2026, 6, 20), 11))[1]
    )


def test_the_calendar_is_the_english_one() -> None:
    assert clocks_change(2026) == (date(2026, 3, 29), date(2026, 10, 25))
    holidays = bank_holidays(2026)
    for day in ("2026-04-03", "2026-04-06", "2026-05-04", "2026-05-25", "2026-08-31"):
        assert date.fromisoformat(day) in holidays
    assert date(2026, 12, 28) in holidays  # Boxing Day falls on a Saturday
    assert workshop_closed(date(2026, 12, 24)) and not workshop_closed(date(2026, 12, 23))
    assert time_of_year(at(date(2026, 12, 10), 17))["days_until_christmas"] == 15


def test_no_shifts_on_bank_holidays() -> None:
    monday = date(2026, 5, 25)  # spring bank holiday
    history = [identity_established_event(at(monday - timedelta(days=6), 6).isoformat())]
    history += work_rota_events(history, PlanningState(), at(monday - timedelta(days=6), 6))
    calendar = project_planning(history).calendar
    assert f"work-rota-{monday.isoformat()}" not in calendar
    assert f"work-rota-{(monday + timedelta(days=1)).isoformat()}" in calendar


def run_year(history: list[DomainEvent], start: date, days: int) -> list[DomainEvent]:
    output: list[DomainEvent] = []
    for offset in range(days):
        for hour in range(8, 23):
            output += seasonal_events(
                [*history, *output],
                at(start + timedelta(days=offset), hour),
                awake=True,
                outdoors=hour in (8, 13),
                rest=0.8,
                names={"mara": "Mara"},
            )
    return output


def test_moments_of_the_year_come_once_each() -> None:
    moments = run_year([], date(2026, 1, 1), 365)
    kinds = [e.payload["kind"] for e in moments if e.kind == "season.moment"]
    for kind in ("clocks-forward", "clocks-back", "shortest-day", "longest-day", "light-evening"):
        assert kinds.count(kind) == 1, kind
    assert kinds.count("bank-holiday") == 7  # with the Boxing Day substitute
    lost_hour = [e for e in moments if e.kind == "needs.changed"]
    assert lost_hour and lost_hour[0].payload["rest"] < 0.8


def test_his_life_starts_to_have_anniversaries() -> None:
    start = date(2026, 1, 5)
    history = [
        identity_established_event(at(start, 6).isoformat()),
        DomainEvent(
            "bond.recognized",
            "pathos",
            {
                "person_id": "mara",
                "bond": "friend",
                "simulated_at": at(start + timedelta(days=40), 20).isoformat(),
            },
        ),
    ]
    output = run_year(history, start + timedelta(days=360), 50)
    anniversaries = [e.payload["text"] for e in output if e.kind == "life.anniversary"]
    assert any("A year today" in text for text in anniversaries)
    assert any("Mara had become a proper friend" in text for text in anniversaries)
