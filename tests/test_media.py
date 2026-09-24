"""Books, series and albums carry across weeks, and he ends up with opinions about them."""

from datetime import datetime, timedelta, timezone

import pytest

from eidos.adapters.standin_gateway import _standin_media_reply
from eidos.application.media import BY_ID, WORKS, current, liking, media_context, media_events
from eidos.domain.events import DomainEvent
from eidos.domain.selfhood import value_evidence

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def live(days: int, *, library_on: tuple[int, ...] = ()) -> list[DomainEvent]:
    history: list[DomainEvent] = []
    for hour in range(days * 24):
        at = START + timedelta(hours=hour)
        at_library = at.day in library_on and at.hour == 11
        history += media_events(
            history,
            at,
            awake=8 <= at.hour <= 22,
            location_id="library" if at_library else "home",
            free=True,
            known_places=frozenset({"home", "library"}),
        )
    return history


@pytest.fixture(scope="module")
def half_year() -> list[DomainEvent]:
    return live(180, library_on=(3, 17))


def test_he_is_usually_partway_through_something_of_each_kind(half_year) -> None:
    started = [e for e in half_year if e.kind == "media.started"]
    assert {BY_ID[e.payload["media_id"]].kind for e in started} == {"book", "series", "album"}
    assert started[0].payload["media_id"] == "piranesi"
    assert set(current(half_year)) <= {"book", "series", "album"}


def test_things_get_finished_or_given_up_with_an_opinion(half_year) -> None:
    ended = [e for e in half_year if e.kind in {"media.finished", "media.abandoned"}]
    assert len(ended) >= 4
    for event in ended:
        work = BY_ID[event.payload["media_id"]]
        assert event.payload["liking"] == liking(work)
        if event.kind == "media.abandoned":
            assert liking(work) <= -0.3 and work.kind != "album"
    finished_books = [
        e
        for e in ended
        if e.kind == "media.finished" and BY_ID[e.payload["media_id"]].kind == "book"
    ]
    assert finished_books
    good = [e for e in finished_books if e.payload["liking"] >= 0.2]
    for event in good:
        assert value_evidence(event)[0][:2] == ("curiosity", 1)


def test_books_come_from_the_library_once_his_shelf_runs_out(half_year) -> None:
    acquired = [e for e in half_year if e.kind == "media.acquired"]
    assert acquired and all(e.payload["from"] == "library" for e in acquired)
    started_books = [
        e.payload["media_id"]
        for e in half_year
        if e.kind == "media.started" and BY_ID[e.payload["media_id"]].kind == "book"
    ]
    assert started_books[:3] == ["piranesi", "station-eleven", "remains"][: len(started_books[:3])]


def test_temperament_decides_and_some_works_just_are_not_for_him() -> None:
    likings = [liking(work) for work in WORKS]
    assert min(likings) < -0.1 < 0.3 < max(likings)
    assert liking(BY_ID["piranesi"]) == liking(BY_ID["piranesi"])


def test_he_can_say_what_he_is_reading(half_year) -> None:
    context = {"identity": {"selfhood": {"reading_watching_listening": media_context(half_year)}}}
    reply = _standin_media_reply("what are you reading at the moment?", context)
    assert reply is not None
    titles = [work.title for work in WORKS]
    assert any(title in reply for title in titles)


def test_without_a_library_he_orders_a_book_after_a_couple_of_weeks() -> None:
    history: list[DomainEvent] = []
    for hour in range(200 * 24):
        at = START + timedelta(hours=hour)
        history += media_events(
            history,
            at,
            awake=8 <= at.hour <= 22,
            location_id="home",
            free=True,
            known_places=frozenset({"home"}),
        )
    online = [e for e in history if e.kind == "media.acquired"]
    assert online and all(e.payload["from"] == "online" for e in online)
