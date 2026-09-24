"""His people: noticing who has become a friend, who is close, and who has drifted.

Relationship numbers move a little with every encounter, kindness and clash. A person
does not experience numbers; now and then they notice that someone has become a proper
friend, that things have gone strained, or that a friendship has faded. This turns the
running relationship state into those rare moments of recognition, at the evening review,
at most one a day. The person talking with him through the app is one of his people too:
that bond is measured from the days you have actually talked, not from a counter.
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.relationships import Relationship

REVIEW_HOUR = 20
FRIEND_WARMTH = 0.5
CLOSE_WARMTH = 0.72
CLOSE_TRUST = 0.45
STRAINED_TENSION = 0.35
SLACK = 0.06  # A bond is not lost the moment it dips below where it formed.
USER = "user"
RANK = {"strained": 0, "drifted": 0, "acquaintance": 1, "friend": 2, "close": 3}


def warmth(relationship: Relationship) -> float:
    return 0.6 * relationship.familiarity + 0.4 * relationship.trust - relationship.tension


def bond_level(relationship: Relationship, current: str | None) -> str:
    slack = SLACK if current in {"friend", "close", "strained"} else 0.0
    if relationship.tension >= STRAINED_TENSION - (slack if current == "strained" else 0.0):
        return "strained"
    felt = warmth(relationship)
    if felt >= CLOSE_WARMTH - (
        slack if current == "close" else 0.0
    ) and relationship.trust >= CLOSE_TRUST - (slack if current == "close" else 0.0):
        return "close"
    if felt >= FRIEND_WARMTH - (slack if current in {"friend", "close"} else 0.0):
        return "friend"
    return "acquaintance"


def user_bond_level(history: Sequence[DomainEvent], at: datetime, current: str | None) -> str:
    """How close you and he are, from the days you have actually talked."""
    days = sorted(
        {
            datetime.fromisoformat(str(event.payload["simulated_at"])).date()
            for event in events_of(history, "conversation.message")
            if event.payload.get("speaker") == "you"
            and isinstance(event.payload.get("simulated_at"), str)
        }
    )
    if not days:
        return "acquaintance"
    quiet = (at.date() - days[-1]).days
    span = (days[-1] - days[0]).days
    if current in {"friend", "close"} and quiet >= 21:
        return "drifted"
    if len(days) >= 15 and span >= 45 and quiet <= 14:
        return "close"
    if len(days) >= 5 and span >= 14:
        return "friend"
    return "acquaintance"


def current_bonds(history: Sequence[DomainEvent]) -> dict[str, str]:
    return {
        str(event.payload["person_id"]): str(event.payload["bond"])
        for event in events_of(history, "bond.recognized")
    }


def bond_events(
    history: Sequence[DomainEvent],
    at: datetime,
    relationships: Mapping[str, Relationship],
    known_person_ids: frozenset[str],
    names: Mapping[str, str],
) -> list[DomainEvent]:
    """At the evening review, notice at most one change in who his people are."""
    if at.hour != REVIEW_HOUR:
        return []
    today = at.date().isoformat()
    if any(
        str(event.payload.get("simulated_at", ""))[:10] == today
        for event in events_of(history, "bond.recognized")
    ):
        return []
    bonds = current_bonds(history)
    changes: list[tuple[int, str, str, str]] = []
    for person_id in sorted(known_person_ids):
        relationship = relationships.get(person_id)
        if relationship is None or relationship.encounters == 0:
            continue
        previous = bonds.get(person_id, "acquaintance")
        now = bond_level(relationship, previous)
        if now != previous:
            changes.append((_salience(previous, now), person_id, previous, now))
    previous = bonds.get(USER, "acquaintance")
    now = user_bond_level(history, at, previous)
    if now != previous and not (previous == "drifted" and now == "acquaintance"):
        changes.append((_salience(previous, now) + 1, USER, previous, now))
    if not changes:
        return []
    _, person_id, previous, now = max(changes)
    text = _recognition(
        names.get(person_id, person_id.replace("-", " ").title()), person_id, previous, now
    )
    recognized = DomainEvent(
        "bond.recognized",
        "pathos",
        {
            "person_id": person_id,
            "bond": now,
            "previous": previous,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=f"bond-{person_id}",
    )
    return [
        recognized,
        DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": text,
                "simulated_at": at.isoformat(),
                "category": "relationship",
                "source": "lived-bond",
                "source_event_id": str(recognized.event_id),
                "person_id": person_id,
                "owner": "pathos",
                "importance": 0.65,
                "confidence": 1.0,
            },
            causation_id=recognized.event_id,
            correlation_id=recognized.correlation_id,
        ),
    ]


def his_people(history: Sequence[DomainEvent], names: Mapping[str, str]) -> list[dict[str, str]]:
    """Who his people are, as he currently feels it, closest first."""
    return [
        {"person": "you" if person_id == USER else names.get(person_id, person_id), "bond": bond}
        for person_id, bond in sorted(
            current_bonds(history).items(), key=lambda item: (-RANK[item[1]], item[0])
        )
        if bond != "acquaintance"
    ]


def _salience(previous: str, now: str) -> int:
    # Growing closer is noticed first, then strain, then quiet fading.
    if RANK[now] > RANK[previous]:
        return 3 + RANK[now]
    return 2 if now in {"strained", "drifted"} else 1


def _recognition(name: str, person_id: str, previous: str, now: str) -> str:
    you = person_id == USER
    if now == "close":
        return (
            "You're one of my closest people now. I don't say that lightly."
            if you
            else f"{name} is one of my closest people now. When did that happen?"
        )
    if now == "friend" and previous == "strained":
        return f"Things feel right again with {name}."
    if now == "friend" and previous in {"close", "drifted"}:
        return (
            "It's good to be talking again."
            if you
            else f"{name} and I aren't as close as we were, but we're still friends."
        )
    if now == "friend":
        return (
            "I think you've become a proper friend, honestly."
            if you
            else f"I think {name}'s become a proper friend."
        )
    if now == "strained":
        return f"Things have got a bit strained with {name}."
    if now == "drifted":
        return "We haven't talked in a while, you and me. I notice it."
    if previous == "strained":
        return f"Things with {name} have settled down, at least."
    return f"{name} and I have drifted a bit."
