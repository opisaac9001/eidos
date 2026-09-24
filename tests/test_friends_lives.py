"""His friends' lives go on: jobs, babies, worries, and sometimes a move away."""

from datetime import datetime, timedelta, timezone

import pytest

from eidos.application.friends_lives import (
    WILL_MOVE,
    _roll,
    away_people,
    busy_people,
    friend_life_events,
    friends_lives,
    friends_lives_context,
)
from eidos.application.npc_movement import npc_movement_events
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import project_npcs

START = datetime(2026, 1, 1, 18, tzinfo=timezone.utc)
FRIENDS = ("mara", "rowan", "nina-vale", "townsfolk-1880")
NAMES = {"mara": "Mara", "rowan": "Rowan", "nina-vale": "Nina Vale", "townsfolk-1880": "Stuart"}


def live(days: int, depths=None, residents=None) -> list[DomainEvent]:
    history: list[DomainEvent] = []
    depths = depths or {person: 5.0 for person in FRIENDS} | {"ellis": 8.0, "user": 9.0}
    for day in range(days):
        at = START + timedelta(days=day)
        history += friend_life_events(
            history,
            at,
            depths=depths,
            first_shared={person: START - timedelta(days=90) for person in depths},
            names=NAMES,
            residents=residents or frozenset({*FRIENDS, "ellis"}),
            known_places=frozenset({"crown-anchor", "cafe"}),
        )
    return history


@pytest.fixture(scope="module")
def years() -> list[DomainEvent]:
    return live(365 * 4)


def news(history: list[DomainEvent]) -> list[DomainEvent]:
    return [e for e in history if e.kind == "friend.life_event"]


def test_friends_have_a_few_real_turns_not_constant_drama(years) -> None:
    turns = [
        e
        for e in news(years)
        if e.payload["kind"] not in {"leaving_do_agreed", "checked_in", "moved_away"}
    ]
    per_year = len(turns) / 4
    assert 2 <= per_year <= 12
    assert all(e.payload["person_id"] in FRIENDS for e in news(years))
    times = [
        datetime.fromisoformat(e.payload["simulated_at"])
        for e in turns
        if e.payload["kind"] not in {"baby_born", "family_better"}
    ]
    assert all(b - a >= timedelta(days=7) for a, b in zip(times, times[1:]))
    memories = {e.payload.get("source_event_id") for e in years if e.kind == "memory.recorded"}
    assert all(str(e.event_id) in memories for e in news(years))


def test_nothing_happens_to_people_he_barely_knows() -> None:
    history = live(365, depths={"mara": 1.0, "rowan": 1.5})
    assert news(history) == []


def test_a_friend_moving_away_gets_a_leaving_do_and_then_is_gone() -> None:
    crowd = {f"friend-{n}": 5.0 for n in range(10)}
    history = live(365 * 6, depths=crowd, residents=frozenset(crowd))
    announced = [e for e in news(history) if e.payload["kind"] == "moving_announced"]
    assert announced, "among ten friends over six years, someone moves away"
    person = announced[0].payload["person_id"]
    year = datetime.fromisoformat(announced[0].payload["simulated_at"]).year
    assert _roll("will-move", person, year) < WILL_MOVE
    agreed = next(
        e
        for e in news(history)
        if e.payload["kind"] == "leaving_do_agreed" and e.payload["person_id"] == person
    )
    booking = next(
        e
        for e in history
        if e.kind == "schedule.created"
        and e.payload["schedule_id"] == agreed.payload["schedule_id"]
    )
    assert booking.causation_id == agreed.event_id
    assert booking.payload["companion_id"] == person
    starts = datetime.fromisoformat(booking.payload["starts_at"])
    assert starts.weekday() in (4, 5)
    moved = next(
        e
        for e in news(history)
        if e.payload["kind"] == "moved_away" and e.payload["person_id"] == person
    )
    assert datetime.fromisoformat(moved.payload["simulated_at"]).date() > starts.date()
    assert person in away_people(history)
    # Never two friends moving away within a year of each other.
    times = [datetime.fromisoformat(e.payload["simulated_at"]) for e in announced]
    assert all(b - a >= timedelta(days=365) for a, b in zip(times, times[1:]))
    # Once gone, nothing more happens to them in town.
    after = [
        e
        for e in news(history)
        if e.payload["person_id"] == person
        and datetime.fromisoformat(e.payload["simulated_at"])
        > datetime.fromisoformat(moved.payload["simulated_at"])
    ]
    assert after == []


def test_a_newborn_or_a_family_worry_keeps_a_friend_busy(years) -> None:
    lives = friends_lives(years)
    worried = [e for e in news(years) if e.payload["kind"] == "family_worry"]
    for worry in worried:
        person = worry.payload["person_id"]
        at = datetime.fromisoformat(worry.payload["simulated_at"]) + timedelta(days=1)
        earlier = [e for e in years if e.kind == "friend.life_event"]
        before = earlier[: earlier.index(worry) + 1]
        assert person in busy_people(before, at)
        kinds = [e.payload["kind"] for e in news(years) if e.payload["person_id"] == person]
        assert "checked_in" in kinds
        if person not in away_people(years):
            assert "family_better" in kinds
    for person, life in lives.people.items():
        if life.baby_born:
            assert life.expecting_since and life.partner_since
            assert life.partner_since < life.expecting_since < life.baby_born


def test_he_can_say_what_is_going_on_with_his_friends(years) -> None:
    last = datetime.fromisoformat(news(years)[-1].payload["simulated_at"])
    context = friends_lives_context(years, last, NAMES)
    assert context and all(item["who"] and item["what"] for item in context)


def test_someone_who_moved_away_stays_off_the_map() -> None:
    now = datetime(2026, 5, 1, 12, tzinfo=timezone.utc)
    moved = DomainEvent(
        "friend.life_event",
        "pathos",
        {
            "person_id": "rowan",
            "kind": "moved_away",
            "text": "Rowan's gone.",
            "moving_to": "Leeds",
            "simulated_at": now.isoformat(),
            "owner": "pathos",
        },
    )
    history: list[DomainEvent] = [moved]
    for hour in range(48):
        history += npc_movement_events(history, now + timedelta(hours=hour))
    assert project_npcs(history, now + timedelta(hours=48)).people["rowan"].location_id == "home"
    rowan_moves = [
        e for e in history if e.kind == "npc.travel_started" and e.payload["actor_id"] == "rowan"
    ]
    assert rowan_moves == []
