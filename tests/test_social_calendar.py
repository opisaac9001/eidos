"""Friends' birthdays and his, bonfire night and New Year's Eve."""

from datetime import date, datetime, timedelta, timezone

import pytest

from eidos.application.social_calendar import (
    _bonfire_night,
    friend_birthday,
    friend_birthday_gifts,
    social_calendar_events,
)
from eidos.domain.events import DomainEvent

START = datetime(2026, 1, 1, 0, tzinfo=timezone.utc)
PLACES = frozenset({"crown-anchor", "cafe", "park", "sports-ground"})


def year(depths, *, where=lambda at, history: "home", care=0.78) -> list[DomainEvent]:
    history: list[DomainEvent] = []
    for hour in range(24 * 366):
        at = START + timedelta(hours=hour)
        history += social_calendar_events(
            history,
            at,
            awake=True,
            location_id=where(at, history),
            depths=depths,
            names={"mara": "Mara", "rowan": "Rowan", "stuart": "Stuart Hart"},
            residents=frozenset(depths),
            unavailable=frozenset(),
            away=frozenset(),
            care=care,
            places=PLACES,
        )
    return history


@pytest.fixture(scope="module")
def with_friends():
    return year({"mara": 7.0, "rowan": 5.0, "stuart": 3.0})


def test_he_marks_the_birthdays_of_friends_he_knows(with_friends) -> None:
    birthdays = [e for e in with_friends if e.kind == "friend.birthday"]
    people = {e.payload["person_id"] for e in birthdays}
    assert people <= {"mara", "rowan"}  # Stuart isn't a close enough friend yet
    for event in birthdays:
        month, day = friend_birthday(event.payload["person_id"])
        when = datetime.fromisoformat(event.payload["simulated_at"]).date()
        assert when in {date(2026, month, day), date(2026, month, day) + timedelta(days=2)}
    mara = next(e for e in birthdays if e.payload["person_id"] == "mara")
    if mara.payload["outcome"] == "remembered":
        assert mara.payload["gift"] and "her" in mara.payload["text"]
        at = datetime.fromisoformat(mara.payload["simulated_at"])
        assert friend_birthday_gifts(with_friends, at)


def test_birthday_drinks_bonfire_and_new_year_are_plans_that_cause_bookings(with_friends) -> None:
    plans = {e.payload["occasion"]: e for e in with_friends if e.kind == "calendar.plan"}
    assert {"his_birthday", "bonfire", "new_year", "birthday_messages"} <= set(plans)
    bookings = [e for e in with_friends if e.kind == "schedule.created"]
    causes = {e.event_id for e in with_friends if e.kind == "calendar.plan"}
    assert bookings and all(e.causation_id in causes for e in bookings)
    bonfire = next(e for e in bookings if e.payload["schedule_id"].startswith("bonfire"))
    assert datetime.fromisoformat(bonfire.payload["starts_at"]).date() == _bonfire_night(2026)
    assert _bonfire_night(2026).weekday() == 5
    assert plans["his_birthday"].payload["companion_id"] == "mara"


def test_alone_new_year_is_a_quiet_night_in() -> None:
    lonely = year({})
    occasions = [e.payload["occasion"] for e in lonely if e.kind == "calendar.plan"]
    assert "new_year_quiet" in occasions and "his_birthday" not in occasions


def test_he_remembers_the_night_if_he_was_there() -> None:
    def at_the_crown(at, history):
        return "crown-anchor" if (at.month, at.day) in {(10, 27)} and at.hour >= 19 else "home"

    history = year({"mara": 7.0, "rowan": 5.0}, where=at_the_crown)
    remembered = [
        e
        for e in history
        if e.kind == "calendar.plan" and e.payload["occasion"].endswith("_remembered")
    ]
    assert [e.payload["occasion"] for e in remembered] == ["his_birthday_remembered"]
