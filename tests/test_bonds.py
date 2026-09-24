"""Friendships deepen through what's shared; deep ones don't fade with time apart."""

from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import _standin_people_reply
from eidos.application.bonds import bond_events, his_people
from eidos.application.friendship import friendships
from eidos.domain.events import DomainEvent
from eidos.domain.relationships import Relationship
from eidos.domain.selfhood import value_evidence

START = datetime(2026, 1, 5, 14, tzinfo=timezone.utc)
NAMES = {"mara": "Mara", "ellis": "Ellis"}


def at(day: int, hour: int = 14) -> datetime:
    return START + timedelta(days=day, hours=hour - 14)


def together(person: str, day: int) -> DomainEvent:
    return DomainEvent(
        "social.activity_completed",
        "pathos",
        {"activity": "conversation", "person_id": person, "simulated_at": at(day).isoformat()},
    )


def through_something(person: str, day: int) -> DomainEvent:
    return DomainEvent(
        "incident.shared_aftermath",
        "pathos",
        {"person_id": person, "outcome": "completed", "simulated_at": at(day).isoformat()},
    )


def talk(day: int, messages: int = 8) -> list[DomainEvent]:
    return [
        DomainEvent(
            "conversation.message",
            "pathos",
            {"speaker": "you", "text": "…", "simulated_at": at(day, 10 + n % 8).isoformat()},
        )
        for n in range(messages)
    ]


def deep_friendship(person: str = "mara") -> list[DomainEvent]:
    history = [together(person, day) for day in range(0, 200, 3)]
    history += [through_something(person, day) for day in (20, 70, 150)]
    return sorted(history, key=lambda e: e.payload["simulated_at"])


def test_without_going_through_anything_together_a_friendship_stays_light() -> None:
    history = [together("ellis", day) for day in range(0, 300, 2)]
    ellis = friendships(history, at(300))["ellis"]
    assert 4 <= ellis.level <= 5


def test_a_deep_friendship_survives_a_long_silence_and_a_light_one_fades() -> None:
    deep = friendships(deep_friendship(), at(200))["mara"]
    assert deep.level >= 6
    year_later = friendships(deep_friendship(), at(560))["mara"]
    assert year_later.level >= deep.level
    assert year_later.out_of_touch(at(560))
    light = [together("ellis", day) for day in range(0, 120, 2)]
    was = friendships(light, at(120))["ellis"].level
    faded = friendships(light, at(400))["ellis"]
    assert was >= 4 and faded.level == 3
    acquaintance = [together("rowan", 0)]
    assert friendships(acquaintance, at(90))["rowan"].depth <= 1.0


def review(history, day, relationships=None, known=frozenset({"mara", "ellis"})):
    return bond_events(history, at(day, 20), relationships or {}, known, NAMES)


def run_reviews(history, days, relationships=None):
    noticed: list[DomainEvent] = []
    for day in days:
        noticed += review([*history, *noticed], day, relationships)
    return noticed


def test_he_notices_friends_becoming_close_and_it_counts_as_care() -> None:
    noticed = run_reviews(deep_friendship(), range(0, 201))
    recognized = [e for e in noticed if e.kind == "bond.recognized"]
    assert [e.payload["bond"] for e in recognized] == ["friend", "close"]
    assert value_evidence(recognized[-1])[0][:2] == ("care", 1)
    gaps = [
        (
            datetime.fromisoformat(b.payload["simulated_at"])
            - datetime.fromisoformat(a.payload["simulated_at"])
        ).days
        for a, b in zip(recognized, recognized[1:])
    ]
    assert all(gap >= 21 for gap in gaps)
    people = his_people([*deep_friendship(), *noticed], NAMES, at(200))
    assert people[0]["person"] == "Mara" and people[0]["level"] >= 6


def test_a_long_gap_with_a_close_friend_is_missed_warmly_and_picked_up_again() -> None:
    history = deep_friendship()
    history += run_reviews(history, range(0, 201))
    later = run_reviews(history, range(201, 300))
    missed = [e for e in later if e.kind == "bond.missed"]
    assert len(missed) == 1 and "no time has passed" in missed[0].payload["text"]
    assert not any(e.payload.get("bond") == "drifted" for e in later)
    assert not any(e.kind == "memory.recorded" and "drifted" in e.payload["text"] for e in later)
    reunion_day = 300
    history = [*history, *later, together("mara", reunion_day)]
    reunion = review(history, reunion_day)
    assert reunion[0].kind == "bond.reunited"
    assert "right where we left off" in reunion[0].payload["text"]


def test_strain_is_a_passing_state_not_a_lost_friendship() -> None:
    history = deep_friendship()
    history += run_reviews(history, range(0, 201))
    clash = {"mara": Relationship("mara", 40, 0.6, 0.9, 0.4)}
    strained = review(history, 201, clash)
    assert strained[0].kind == "bond.strained"
    history += strained
    eased = review(history, 205, {"mara": Relationship("mara", 40, 0.6, 0.9, 0.1)})
    assert eased[0].kind == "bond.eased"
    assert his_people([*history, *eased], NAMES, at(205))[0]["bond"] in {"close", "closest"}


def test_you_stay_a_close_friend_through_a_quiet_month() -> None:
    history: list[DomainEvent] = []
    for day in range(0, 200, 2):
        history += talk(day)
    you = friendships(history, at(200))["user"]
    assert you.level >= 6
    history += run_reviews(history, range(0, 201))
    assert any(
        e.payload.get("person_id") == "user" and e.payload.get("bond") in {"close", "closest"}
        for e in history
    )
    quiet = run_reviews(history, range(201, 260))
    assert not any(e.payload.get("bond") == "drifted" for e in quiet)
    missed = [e for e in quiet if e.kind == "bond.missed"]
    assert missed and "still one of my people" in missed[0].payload["text"]
    context = {"identity": {"selfhood": {"his_people": his_people(history, NAMES, at(230))}}}
    reply = str(_standin_people_reply("are we friends?", context))
    assert "count on" in reply or "closest" in reply
    stranger = {"identity": {"selfhood": {"his_people": []}}}
    assert "getting to know you" in str(_standin_people_reply("are we friends?", stranger))


def test_a_lighter_friendship_can_drift_without_a_falling_out() -> None:
    history = [together("ellis", day) for day in range(0, 120, 2)]
    history += run_reviews(history, range(0, 121))
    assert any(e.payload.get("bond") == "friend" for e in history)
    later = run_reviews(history, range(121, 400))
    drifted = [e for e in later if e.payload.get("bond") == "drifted"]
    assert drifted and "No falling out" in drifted[0].payload["text"]


def test_missing_a_close_friend_makes_him_want_to_get_in_touch() -> None:
    from eidos.application.followups import follow_up_events

    history = deep_friendship()
    history += run_reviews(history, range(0, 201))
    history += run_reviews(history, range(201, 300))
    missed = next(e for e in history if e.kind == "bond.missed")
    scheduled = [
        e
        for e in follow_up_events(history, at(300))
        if e.kind == "follow_up.scheduled" and e.payload["source_event_id"] == str(missed.event_id)
    ]
    assert scheduled and scheduled[0].payload["person_id"] == "mara"
    assert "catch up" in scheduled[0].payload["reason"]
    you = DomainEvent(
        "bond.missed",
        "pathos",
        {"person_id": "user", "text": "…", "simulated_at": at(300).isoformat()},
    )
    assert not [
        e
        for e in follow_up_events([you], at(300))
        if e.payload.get("source_event_id") == str(you.event_id)
    ]
