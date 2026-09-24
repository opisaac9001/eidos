"""His people: noticing who has become a friend, who is close, and who he misses.

Friendship depth lives in ``application/friendship.py``; a person does not experience it
as a number. At the evening review he may notice one thing a day about his people:

* someone has become a friend (level 4), a close friend (6), or one of his closest people
  (9 and above);
* a lighter friendship has faded ("we've drifted a bit"). Only friendships below level 6
  can fade: a close friend stays a close friend;
* things have gone strained, or feel right again. Strain is a passing state, not a lost
  friendship;
* he hasn't seen a close friend in ages. That is warmth, not loss, and when they meet again
  they pick up where they left off.

The person talking with him through the app is one of his people too, by the same rules:
a close friend who goes quiet for a month is still a close friend.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.application.friendship import USER, Friendship, friendships
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.relationships import Relationship

REVIEW_HOUR = 20
STRAINED_TENSION = 0.35
EASED_TENSION = 0.2
SETTLE = timedelta(days=21)  # how close someone is isn't re-decided every few days
RANK = {"acquaintance": 1, "drifted": 1, "friend": 2, "close": 3, "closest": 4}
FRIENDLY = frozenset({"friend", "close", "closest"})
NOTICING = ("bond.recognized", "bond.strained", "bond.eased", "bond.missed", "bond.reunited")


def bond_for(level: int) -> str:
    if level >= 9:
        return "closest"
    if level >= 6:
        return "close"
    return "friend" if level >= 4 else "acquaintance"


def current_bonds(history: Sequence[DomainEvent]) -> dict[str, str]:
    """How he last recognised each person: acquaintance, friend, close, closest, drifted."""
    return {
        str(event.payload["person_id"]): str(event.payload["bond"])
        for event in events_of(history, "bond.recognized")
    }


def strained_with(history: Sequence[DomainEvent]) -> frozenset[str]:
    strained: set[str] = set()
    for event in events_of(history, "bond.strained", "bond.eased"):
        person = str(event.payload.get("person_id"))
        if event.kind == "bond.strained":
            strained.add(person)
        else:
            strained.discard(person)
    return frozenset(strained)


def bond_events(
    history: Sequence[DomainEvent],
    at: datetime,
    relationships: Mapping[str, Relationship],
    known_person_ids: frozenset[str],
    names: Mapping[str, str],
) -> list[DomainEvent]:
    """At the evening review, notice at most one thing about his people."""
    if at.hour != REVIEW_HOUR:
        return []
    today = at.date().isoformat()
    if any(
        str(event.payload.get("simulated_at", ""))[:10] == today
        for event in events_of(history, *NOTICING)
    ):
        return []
    bonds = current_bonds(history)
    strained = strained_with(history)
    last_recognised = {
        str(event.payload["person_id"]): datetime.fromisoformat(str(event.payload["simulated_at"]))
        for event in events_of(history, "bond.recognized")
    }
    missed_since = {
        str(event.payload["person_id"]): str(event.payload.get("last_shared"))
        for event in events_of(history, "bond.missed")
    }
    reunited = {
        (str(event.payload["person_id"]), str(event.payload.get("shared_at")))
        for event in events_of(history, "bond.reunited")
    }
    candidates: list[tuple[int, str, str, dict[str, object]]] = []
    for person_id, friendship in friendships(history, at).items():
        if person_id != USER and person_id not in known_person_ids:
            continue
        name = "you" if person_id == USER else names.get(person_id, _title(person_id))
        previous = bonds.get(person_id, "acquaintance")
        now = bond_for(friendship.level)
        settled = person_id not in last_recognised or at - last_recognised[person_id] >= SETTLE
        if RANK[now] > RANK[previous] and settled:
            grown = _grown(friendship, name, now, previous)
            candidates.append((5 + RANK[now], "bond.recognized", person_id, grown))
        elif previous in FRIENDLY and now == "acquaintance" and settled:
            candidates.append((3, "bond.recognized", person_id, _faded(name, person_id)))
        relationship = relationships.get(person_id)
        if relationship is not None and person_id != USER and friendship.level >= 4:
            if person_id not in strained and relationship.tension >= STRAINED_TENSION:
                candidates.append((4, "bond.strained", person_id, _strain(name, True)))
            elif person_id in strained and relationship.tension <= EASED_TENSION:
                candidates.append((4, "bond.eased", person_id, _strain(name, False)))
        last = friendship.last_shared.isoformat()
        if friendship.out_of_touch(at) and missed_since.get(person_id) != last:
            candidates.append((2, "bond.missed", person_id, _missed(friendship, name, at)))
        if (
            friendship.level >= 6
            and friendship.days_apart_before_last >= 45
            and friendship.last_shared.date() == at.date()
            and (person_id, last) not in reunited
        ):
            candidates.append((6, "bond.reunited", person_id, _reunion(friendship, name)))
    if not candidates:
        return []
    _, kind, person_id, payload = max(candidates, key=lambda item: (item[0], item[2]))
    event = DomainEvent(
        kind,
        "pathos",
        {"person_id": person_id, **payload, "simulated_at": at.isoformat(), "owner": "pathos"},
        correlation_id=f"bond-{person_id}",
    )
    return [
        event,
        DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": payload["text"],
                "simulated_at": at.isoformat(),
                "category": "relationship",
                "source": "lived-bond",
                "source_event_id": str(event.event_id),
                "person_id": person_id,
                "owner": "pathos",
                "importance": 0.65 if kind == "bond.recognized" else 0.5,
                "confidence": 1.0,
            },
            causation_id=event.event_id,
            correlation_id=event.correlation_id,
        ),
    ]


def his_people(
    history: Sequence[DomainEvent], names: Mapping[str, str], at: datetime | None = None
) -> list[dict[str, object]]:
    """Who his people are, as he currently feels it, closest first."""
    bonds = current_bonds(history)
    depth = friendships(history, at) if at is not None else {}
    strained = strained_with(history)
    people: list[dict[str, object]] = []
    for person_id, bond in sorted(bonds.items(), key=lambda item: (-RANK[item[1]], item[0])):
        if bond not in FRIENDLY:
            continue
        friendship = depth.get(person_id)
        people.append(
            {
                "person": "you" if person_id == USER else names.get(person_id, _title(person_id)),
                "bond": bond,
                "level": friendship.level if friendship else None,
                "what_they_are_to_him": friendship.name if friendship else None,
                "strained": person_id in strained,
                "out_of_touch": bool(friendship and at and friendship.out_of_touch(at)),
            }
        )
    return people


# -- how he'd put it --------------------------------------------------------------------


def _grown(friendship: Friendship, name: str, now: str, previous: str) -> dict[str, object]:
    you = name == "you"
    if now == "closest":
        text = (
            "You're one of my closest people now. I don't say that lightly."
            if you
            else f"{name} is one of my closest people now. When did that happen?"
        )
    elif now == "close":
        text = (
            "I think you've become a real friend. Someone I can actually count on."
            if you
            else f"{name} is someone I can count on now. A real friend."
        )
    elif previous == "drifted":
        text = "It's good to be talking again." if you else f"Good to have {name} back in my life."
    else:
        text = (
            "I think you've become a proper friend, honestly."
            if you
            else f"I think {name} has become a proper friend."
        )
    return {
        "bond": now,
        "previous": previous,
        "level": friendship.level,
        "what_they_are_to_him": friendship.name,
        "text": text,
    }


def _faded(name: str, person_id: str) -> dict[str, object]:
    text = (
        "We haven't talked in a long while, you and me. I notice it."
        if person_id == USER
        else f"{name} and I have drifted a bit. No falling out, just life."
    )
    return {"bond": "drifted", "previous": "friend", "level": 3, "text": text}


def _strain(name: str, strained: bool) -> dict[str, object]:
    return {
        "text": f"Things have got a bit strained with {name}."
        if strained
        else f"Things feel right again with {name}."
    }


def _missed(friendship: Friendship, name: str, at: datetime) -> dict[str, object]:
    weeks = (at - friendship.last_shared).days // 7
    text = (
        f"We haven't talked in about {weeks} weeks. I hope you're alright. No rush; you're "
        "still one of my people."
        if name == "you"
        else f"Haven't seen {name} in about {weeks} weeks. It'll be like no time has passed "
        "when we do."
    )
    return {"last_shared": friendship.last_shared.isoformat(), "weeks": weeks, "text": text}


def _reunion(friendship: Friendship, name: str) -> dict[str, object]:
    weeks = friendship.days_apart_before_last // 7
    text = (
        f"Talking again after {weeks} weeks, and it was like no time had passed."
        if name == "you"
        else f"Saw {name} for the first time in {weeks} weeks. Picked up right where we left off."
    )
    return {"shared_at": friendship.last_shared.isoformat(), "weeks": weeks, "text": text}


def _title(person_id: str) -> str:
    return person_id.replace("-", " ").title()
