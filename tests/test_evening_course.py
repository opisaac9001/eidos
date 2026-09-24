"""An autumn evening class, finished or not."""

from datetime import date, datetime, timedelta, timezone

from eidos.application.economy import financial_foundation_events
from eidos.application.evening_course import (
    COURSES,
    SESSIONS,
    _roll,
    course_context,
    course_fee,
    evening_course_events,
)
from eidos.domain.events import DomainEvent

OPENED = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
VALUES = {"craft": 0.72, "curiosity": 0.84, "autonomy": 0.68, "care": 0.78}


def enrolling_year() -> int:
    return next(year for year in range(2026, 2040) if _roll("enrol", year) < 0.6)


def first_sunday_of_september(year: int) -> datetime:
    day = next(date(year, 9, n) for n in range(1, 8) if date(year, 9, n).weekday() == 6)
    return datetime(year, 9, day.day, 19, tzinfo=timezone.utc)


def term(*, attend, worn_out=False, balance=100_000):
    year = enrolling_year()
    history: list[DomainEvent] = financial_foundation_events([], OPENED.replace(year=year - 1))
    calendar: dict[str, str] = {}
    at = first_sunday_of_september(year)
    for hour in range(0, 24 * 90):
        now = at + timedelta(hours=hour)
        output = evening_course_events(
            history,
            now,
            awake=True,
            values=VALUES,
            balance_pence=balance,
            rent_pence=12_500,
            calendar=calendar,
            venue="community-hall",
            worn_out=worn_out,
        )
        for event in output:
            if event.kind == "schedule.created":
                calendar[event.payload["schedule_id"]] = "scheduled"
            if event.kind == "schedule.cancelled":
                calendar[event.payload["schedule_id"]] = "cancelled"
        history += output
        for schedule_id, status in list(calendar.items()):
            week = int(schedule_id.rsplit("-", 1)[1])
            if status == "scheduled" and now.hour == 22 and attend(week):
                starts = next(
                    datetime.fromisoformat(e.payload["starts_at"])
                    for e in history
                    if e.kind == "schedule.created" and e.payload["schedule_id"] == schedule_id
                )
                if starts.date() == now.date():
                    calendar[schedule_id] = "completed"
    return history


def stages(history) -> list[str]:
    return [e.payload["stage"] for e in history if e.kind == "course.stage"]


def test_he_signs_up_in_september_for_ten_tuesdays() -> None:
    history = term(attend=lambda week: True)
    enrolled = next(e for e in history if e.kind == "course.stage")
    assert enrolled.payload["course_id"] in {course[0] for course in COURSES.values()}
    sessions = [e for e in history if e.kind == "schedule.created"]
    assert len(sessions) == SESSIONS
    assert all(datetime.fromisoformat(e.payload["starts_at"]).weekday() == 1 for e in sessions)
    assert all(e.causation_id == enrolled.event_id for e in sessions)
    at = datetime.fromisoformat(enrolled.payload["simulated_at"])
    assert course_fee(history, at)[0][1] == enrolled.payload["fee_pence"]


def test_going_most_weeks_means_finishing_it() -> None:
    history = term(attend=lambda week: True)
    assert stages(history)[-1] == "finished"
    assert course_context(history)["status"] == "finished it"


def test_stopping_after_a_few_weeks_is_one_more_thing_not_finished() -> None:
    history = term(attend=lambda week: week <= 3)
    assert stages(history)[-1] == "dropped"
    assert "didn't finish" in history[-1].payload["text"]


def test_worn_out_he_skips_some_tuesdays() -> None:
    skipped = [
        e for e in term(attend=lambda week: True, worn_out=True) if e.kind == "schedule.cancelled"
    ]
    assert 1 <= len(skipped) <= SESSIONS - 1


def test_not_if_the_fee_would_leave_him_short() -> None:
    assert stages(term(attend=lambda week: True, balance=20_000)) == []
