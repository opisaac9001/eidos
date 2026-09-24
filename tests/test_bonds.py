"""He notices, now and then, who has become one of his people, and that includes you."""

from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import _standin_people_reply
from eidos.application.bonds import bond_events, bond_level, his_people, user_bond_level
from eidos.domain.events import DomainEvent
from eidos.domain.relationships import Relationship
from eidos.domain.selfhood import value_evidence

EVENING = datetime(2026, 3, 2, 20, tzinfo=timezone.utc)
NAMES = {"mara": "Mara Okafor", "ellis": "Ellis Grant"}


def review(history, at, relationships):
    return bond_events(history, at, relationships, frozenset(relationships), NAMES)


def test_warmth_becomes_friendship_and_trust_makes_someone_close() -> None:
    assert bond_level(Relationship("mara", 5, 0.3, 0.3, 0.0), None) == "acquaintance"
    assert bond_level(Relationship("mara", 20, 0.4, 0.7, 0.0), None) == "friend"
    assert bond_level(Relationship("mara", 40, 0.4, 1.0, 0.0), None) == "friend"
    assert bond_level(Relationship("mara", 40, 0.55, 0.95, 0.0), None) == "close"
    assert bond_level(Relationship("mara", 40, 0.55, 0.95, 0.4), "close") == "strained"
    # A dip just below where a bond formed does not undo it.
    assert bond_level(Relationship("mara", 40, 0.4, 0.62, 0.0), "friend") == "friend"


def test_he_notices_one_change_an_evening_and_it_counts_as_care() -> None:
    relationships = {
        "mara": Relationship("mara", 20, 0.4, 0.7, 0.0),
        "ellis": Relationship("ellis", 60, 0.4, 0.8, 0.0),
    }
    first = review([], EVENING, relationships)
    assert first[0].kind == "bond.recognized" and first[0].payload["bond"] == "friend"
    assert value_evidence(first[0])[0][:2] == ("care", 1)
    assert review(first, EVENING, relationships) == []
    assert review([], EVENING.replace(hour=12), relationships) == []
    second = review(first, EVENING + timedelta(days=1), relationships)
    assert second[0].payload["person_id"] != first[0].payload["person_id"]
    people = his_people([*first, *second], NAMES)
    assert {item["person"] for item in people} == {"Mara Okafor", "Ellis Grant"}


def talk(day: int) -> DomainEvent:
    return DomainEvent(
        "conversation.message",
        "pathos",
        {
            "text": "Hi.",
            "speaker": "you",
            "simulated_at": (EVENING - timedelta(days=60 - day)).isoformat(),
        },
    )


def test_you_become_a_friend_by_actually_talking_and_can_drift() -> None:
    assert user_bond_level([talk(0), talk(1)], EVENING, None) == "acquaintance"
    friends = [talk(day) for day in range(0, 60, 3)]
    assert user_bond_level(friends, EVENING, None) == "close"
    few = [talk(day) for day in (0, 5, 10, 15, 20)]
    assert user_bond_level(few, EVENING - timedelta(days=30), None) == "friend"
    assert user_bond_level(few, EVENING, "friend") == "drifted"
    recognized = review(friends, EVENING, {})
    assert recognized[0].payload["person_id"] == "user"
    assert "closest" in recognized[0].payload["text"]
    context = {"identity": {"selfhood": {"his_people": his_people(recognized, NAMES)}}}
    assert "closest" in str(_standin_people_reply("are we friends?", context))
    stranger = {"identity": {"selfhood": {"his_people": []}}}
    assert "getting to know you" in str(_standin_people_reply("are we friends?", stranger))
