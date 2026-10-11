"""His free time is lived moment to moment: habit, feeling and passing thoughts choose it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.everyday import (
    REPERTOIRE,
    _answers,
    _habit,
    _primed,
    _urges,
    need_restored,
    repertoire,
)
from eidos.application.life import Life
from eidos.domain.events import DomainEvent

AT = datetime(2026, 3, 4, 8, 0, tzinfo=timezone.utc)
DOING = {doing.kind: doing for doing in REPERTOIRE}


@pytest.fixture(scope="module")
def two_days(tmp_path_factory) -> list[DomainEvent]:
    """Two days lived as the server lives them, a few minutes at a time."""
    life = Life(
        SQLiteEventStore(tmp_path_factory.mktemp("everyday") / "w.sqlite3"), StandInGateway()
    )
    for _ in range(2 * 24 * 12):
        life.advance(1 / 12)
    return life.history()


def _when(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def test_free_time_fills_with_ordinary_things_each_his_own_choice(two_days) -> None:
    chosen = [event for event in two_days if event.kind == "everyday.chosen"]
    assert len(chosen) >= 15
    assert len({event.payload["activity_type"] for event in chosen}) >= 6
    by_id = {event.event_id: event for event in two_days}
    for booking in (
        event
        for event in two_days
        if event.kind == "schedule.created"
        and str(event.payload["schedule_id"]).startswith("doing-")
    ):
        cause = by_id[booking.causation_id]
        while cause.kind != "everyday.chosen":
            cause = by_id[cause.causation_id]
        assert cause.payload["activity_type"] == booking.payload["activity_type"]
    # And they are actually lived, not just booked.
    realized = [
        event
        for event in two_days
        if event.kind == "agency.activity_realized"
        and str(event.payload["schedule_id"]).startswith("doing-")
    ]
    assert len(realized) >= 0.7 * len(chosen)


def test_choices_are_made_to_the_minute_not_on_the_hour(two_days) -> None:
    minutes = {_when(event).minute for event in two_days if event.kind == "everyday.chosen"}
    assert minutes - {0}


def test_never_while_asleep_or_two_things_at_once(two_days) -> None:
    asleep = False
    for event in two_days:
        if event.kind == "sleep.started":
            asleep = True
        elif event.kind == "sleep.ended":
            asleep = False
        elif event.kind == "everyday.chosen":
            assert not asleep
    spans = sorted(
        (
            datetime.fromisoformat(str(event.payload["starts_at"])),
            datetime.fromisoformat(str(event.payload["ends_at"])),
        )
        for event in two_days
        if event.kind == "schedule.created"
        and event.payload.get("actor_id") in {None, "pathos"}
        and event.payload.get("ends_at")
    )
    # Something he planned since can land on a doing; then the doing is cut short for it.
    cut = {
        str(event.payload["schedule_id"])
        for event in two_days
        if event.kind == "schedule.cancelled"
        and str(event.payload["reason"]).startswith("Put it down")
    }
    doings = [
        (
            datetime.fromisoformat(str(event.payload["starts_at"])),
            datetime.fromisoformat(str(event.payload["ends_at"])),
        )
        for event in two_days
        if event.kind == "schedule.created"
        and str(event.payload["schedule_id"]).startswith("doing-")
        and str(event.payload["schedule_id"]) not in cut
    ]
    for start, end in doings:
        overlapping = [span for span in spans if span[0] < end and start < span[1]]
        assert overlapping == [(start, end)]


def test_what_he_just_chose_cannot_slip_his_mind(two_days) -> None:
    assert not any(
        event.kind == "prospective_memory.lapsed"
        and str(event.payload["schedule_id"]).startswith("doing-")
        for event in two_days
    )


def test_finishing_a_cup_of_tea_is_not_an_occasion_for_deliberation(two_days) -> None:
    doing_events = {
        str(event.event_id)
        for event in two_days
        if str(event.payload.get("schedule_id", "")).startswith("doing-")
        or str(event.payload.get("intention_id", "")).startswith("doing-")
    }
    assert not any(
        event.kind == "agency.deliberation_requested"
        and event.payload["source_event_id"] in doing_events
        for event in two_days
    )


def test_a_finished_doing_gives_back_what_it_serves() -> None:
    assert need_restored("nap") == ("rest", 0.15)
    assert need_restored("camera_walk") == ("curiosity", 0.06)
    assert need_restored("something_new") is None


def _realized(kind: str, at: datetime, schedule_id: str = "doing-x-schedule") -> DomainEvent:
    return DomainEvent(
        "agency.activity_realized",
        "pathos",
        {
            "schedule_id": schedule_id,
            "activity_type": kind,
            "title": "Make a pot of filter coffee",
            "location_id": "home",
            "action": "work",
            "simulated_at": at.isoformat(),
        },
    )


def test_habits_are_learned_by_repetition_at_a_time_of_day_and_fade() -> None:
    coffee = DOING["filter_coffee"]
    none = _habit([], coffee, AT)
    week = [_realized("filter_coffee", AT - timedelta(days=day)) for day in range(1, 8)]
    learned = _habit(week, coffee, AT)
    assert none == 0 and learned > 0.6
    # Not at a different time of day,
    assert _habit(week, coffee, AT.replace(hour=20)) < 0.1
    # and less and less, the longer it's been since he did it.
    long_ago = [_realized("filter_coffee", AT - timedelta(days=day)) for day in range(20, 27)]
    assert _habit(long_ago, coffee, AT) < learned / 2


def test_a_passing_thought_leads_to_the_thing_it_was_about() -> None:
    coffee = DOING["filter_coffee"]
    assert _primed(coffee, coffee.title, ["Could murder a coffee."]) == "Could murder a coffee."
    assert _primed(coffee, coffee.title, ["Rain on the window again."]) is None
    book = DOING["read_book"]
    title = book.title.format(title="Piranesi")
    assert _primed(book, title, ["Wonder what happens in Piranesi next."])


def test_a_nagging_pull_weighs_in_for_a_while() -> None:
    felt = DomainEvent("impulse.felt", "pathos", {"kind": "out", "simulated_at": AT.isoformat()})
    assert _urges([felt], AT + timedelta(minutes=20)) == {"out"}
    assert _urges([felt], AT + timedelta(hours=2)) == frozenset()
    assert _answers(DOING["river_walk"], frozenset({"out"}))
    assert not _answers(DOING["sofa"], frozenset({"out"}))
    assert _answers(DOING["sofa"], frozenset({"rest"}))


def test_his_own_new_idea_that_he_enjoyed_joins_what_he_does() -> None:
    at = AT - timedelta(days=2)
    idea = _realized("bridge_sketching", at, "pathos-agency-cause-1-schedule")
    felt = DomainEvent(
        "experience.felt",
        "pathos",
        {"activity_type": "bridge_sketching", "enjoyment": 0.6, "simulated_at": at.isoformat()},
    )
    kinds = {doing.kind for doing in repertoire([idea, felt])}
    assert "bridge_sketching" in kinds
    disliked = DomainEvent(
        "experience.felt",
        "pathos",
        {"activity_type": "bridge_sketching", "enjoyment": -0.2, "simulated_at": at.isoformat()},
    )
    assert "bridge_sketching" not in {doing.kind for doing in repertoire([idea, disliked])}


def test_sitting_down_with_his_book_is_how_he_gets_through_it(two_days) -> None:
    read = [
        event
        for event in two_days
        if event.kind == "agency.activity_realized"
        and event.payload.get("activity_type") in {"read_book", "watch_series", "listen_album"}
    ]
    progressed = {
        event.payload.get("after_doing") for event in two_days if event.kind == "media.progressed"
    }
    if read:
        assert progressed & {event.payload["schedule_id"] for event in read}


def test_he_puts_the_kettle_down_when_you_come_round(tmp_path) -> None:
    from eidos.application.everyday import doing_now

    life = Life(SQLiteEventStore(tmp_path / "w.sqlite3"), StandInGateway())
    life.advance(8)
    for _ in range(36):
        if doing_now(
            life._planning(life.history()), life._project_state(life.history()).simulated_at
        ):
            break
        life.advance(1 / 12)
    else:
        pytest.skip("never caught him in the middle of something")
    life.request_visit("kettle")
    kinds = [event.kind for event in life.history()[-6:]]
    assert "visit.accepted" in kinds
    cancelled = [
        event
        for event in life.history()
        if event.kind == "schedule.cancelled"
        and str(event.payload["schedule_id"]).startswith("doing-")
    ]
    assert cancelled and cancelled[-1].payload["reason"] == "Put it down when you came round."
