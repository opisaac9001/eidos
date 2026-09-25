"""Falling out with a friend, and making up (or, with a newer friend, not)."""

from datetime import datetime, timedelta, timezone

from eidos.application.falling_out import (
    AFTER_LETTING_DOWN,
    _roll,
    estranged,
    falling_out_context,
    falling_out_events,
)
from eidos.application.friends_lives import busy_people
from eidos.domain.relationships import project_relationships

START = datetime(2026, 1, 1, 20, tzinfo=timezone.utc)
VALUES = {"care": 0.78, "reliability": 0.74}


def live(days, depth, *, let_down_on=None, person="mara"):
    history = []
    for day in range(days):
        at = START + timedelta(days=day)
        history += falling_out_events(
            history,
            at,
            depths={person: depth, "ellis": depth, "user": depth},
            names={person: person.title()},
            residents=frozenset({person, "ellis"}),
            unavailable=frozenset(),
            values=VALUES,
            let_down=frozenset({person}) if day == let_down_on else frozenset(),
        )
    return history


def stages(history):
    return [e.payload["stage"] for e in history if e.kind == "friend.falling_out"]


def first_fall(person="mara") -> int:
    return next(
        day
        for day in range(3000)
        if _roll("fall-out", person, (START + timedelta(days=day)).date().isoformat())
        < AFTER_LETTING_DOWN
    )


def test_letting_someone_down_can_lead_to_a_falling_out_that_strains_the_bond() -> None:
    day = first_fall()
    history = live(day + 1, 4.0, let_down_on=day)
    assert stages(history) == ["fell_out"]
    assert project_relationships(history).relationships["mara"].tension >= 0.35
    assert "mara" in estranged(history)
    assert "mara" in busy_people(history, START + timedelta(days=day))
    assert falling_out_context(history, {"mara": "Mara"})[0]["who"] == "Mara"
    assert all(e.payload["person_id"] != "ellis" for e in history if e.kind.startswith("friend"))


def test_a_close_friend_always_comes_back_round() -> None:
    day = first_fall()
    history = live(day + 200, 7.0, let_down_on=day)
    assert stages(history)[0] == "fell_out"
    assert stages(history)[-1] == "made_up"
    assert "drifted_apart" not in stages(history)
    assert "mara" not in estranged(history)
    assert project_relationships(history).relationships["mara"].tension < 0.2


def test_with_newer_friends_it_sometimes_never_mends() -> None:
    outcomes = set()
    for n in range(30):
        person = f"friend-{n}"
        day = first_fall(person)
        history = live(day + 150, 4.0, let_down_on=day, person=person)
        outcomes.add(stages(history)[-1])
    assert outcomes <= {"made_up", "drifted_apart", "no_reply", "fell_out"}
    assert {"made_up", "drifted_apart"} <= outcomes


def test_falling_outs_stay_rare() -> None:
    history = []
    friends = [f"friend-{n}" for n in range(8)]
    for day in range(365):
        at = START + timedelta(days=day)
        history += falling_out_events(
            history,
            at,
            depths={person: 4.0 for person in friends},
            names={},
            residents=frozenset(friends),
            unavailable=frozenset(),
            values=VALUES,
            let_down=frozenset(friends),  # he lets everyone down all the time
            first_shared={person: START - timedelta(days=200) for person in friends},
        )
    rifts = [e for e in history if e.payload.get("stage") == "fell_out"]
    assert 1 <= len(rifts) <= 3  # the six-month gap is the ceiling
    new_friend = falling_out_events(
        [],
        START,
        depths={"mara": 4.0},
        names={},
        residents=frozenset({"mara"}),
        unavailable=frozenset(),
        values=VALUES,
        let_down=frozenset({"mara"}),
        first_shared={"mara": START - timedelta(days=20)},
    )
    assert new_friend == []
