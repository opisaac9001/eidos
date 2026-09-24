"""Memories that come back on their own.

People mostly remember when something sets it off, not when asked. Sitting in the Crown
brings back the night of Rowan's leaving do. A year to the day after Dad's heart scare, he's
quiet all evening without quite knowing why at first. Walking past a friend's old haunt
after they've moved away, he nearly messages to see if they fancy a pint.

Three triggers:
- **A place:** somewhere a memory that mattered happened, more than a month ago.
- **An anniversary:** a year to the day since something important.
- **Missing someone:** a close friend who has moved away.

At most one memory surfaces a day, and the same one not again for three months. Each is a
``memory.surfaced`` event with a short memory of the moment, so it can shape how he feels
and what he talks about.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

KIND = "memory.surfaced"
SOURCE = "lived-surfaced"
PLACE_CHANCE = 0.12  # per hour he's somewhere a memory lives
MISSING_CHANCE = 0.05  # per evening, for a close friend who has moved away
MIN_IMPORTANCE = 0.6
ANNIVERSARY_IMPORTANCE = 0.7
OLDER_THAN = timedelta(days=30)
NOT_AGAIN_FOR = timedelta(days=90)
MISSING_GAP = timedelta(days=21)
QUIET_PLACES = frozenset({"home", "in_transit", "in-transit", "workshop"})


def surfacing_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    location_id: str,
    place_names: Mapping[str, str],
    names: Mapping[str, str],
    away: Mapping[str, str],
    depths: Mapping[str, float],
) -> list[DomainEvent]:
    """Something from before, come back for a moment. ``away`` maps friend -> city."""
    if not awake:
        return []
    today = at.date().isoformat()
    surfaced = events_of(history, KIND)
    if surfaced and str(surfaced[-1].payload.get("simulated_at", ""))[:10] == today:
        return []
    return (
        _anniversary(history, at, surfaced)
        or _missing(history, at, surfaced, names, away, depths)
        or _place(history, at, surfaced, location_id, place_names)
    )


def _recent_sources(surfaced: Sequence[DomainEvent], at: datetime) -> set[str]:
    return {
        str(e.payload.get("source_memory_id")) for e in surfaced if at - _time(e) < NOT_AGAIN_FOR
    }


def _memories(history: Sequence[DomainEvent]) -> list[DomainEvent]:
    return [
        e
        for e in events_of(history, "memory.recorded")
        if e.payload.get("owner", "pathos") == "pathos"
        and e.payload.get("source") != SOURCE
        and isinstance(e.payload.get("text"), str)
        and isinstance(e.payload.get("simulated_at"), str)
    ]


def _place(
    history: Sequence[DomainEvent],
    at: datetime,
    surfaced: Sequence[DomainEvent],
    location_id: str,
    place_names: Mapping[str, str],
) -> list[DomainEvent]:
    if location_id in QUIET_PLACES or not 9 <= at.hour <= 22:
        return []
    if _roll("place", location_id, at.isoformat()) >= PLACE_CHANCE:
        return []
    recent = _recent_sources(surfaced, at)
    candidates = [
        e
        for e in _memories(history)
        if e.payload.get("location_id") == location_id
        and float(e.payload.get("importance", 0.0)) >= MIN_IMPORTANCE
        and at - _time(e) >= OLDER_THAN
        and str(e.event_id) not in recent
    ]
    if not candidates:
        return []
    candidates.sort(key=lambda e: float(e.payload.get("importance", 0.0)), reverse=True)
    memory = candidates[int(_roll("which", at.isoformat()) * min(5, len(candidates)))]
    place = place_names.get(location_id, location_id.replace("-", " "))
    text = f"Being at {place} brought something back, out of nowhere: {_gist(memory)}"
    return _surface(memory, "place", text, at, lift=0.05)


def _anniversary(
    history: Sequence[DomainEvent], at: datetime, surfaced: Sequence[DomainEvent]
) -> list[DomainEvent]:
    if at.hour != 20:
        return []
    recent = _recent_sources(surfaced, at)
    for years in (1, 2, 3):
        try:
            then = at.replace(year=at.year - years).date()
        except ValueError:
            continue  # 29 February
        for memory in _memories(history):
            if (
                _time(memory).date() == then
                and float(memory.payload.get("importance", 0.0)) >= ANNIVERSARY_IMPORTANCE
                and str(memory.event_id) not in recent
            ):
                span = "A year" if years == 1 else f"{years} years"
                text = (
                    f"{span} ago today: {_gist(memory)} Strange how fast that went, and how slow."
                )
                return _surface(memory, "anniversary", text, at, lift=0.0)
    return []


def _missing(
    history: Sequence[DomainEvent],
    at: datetime,
    surfaced: Sequence[DomainEvent],
    names: Mapping[str, str],
    away: Mapping[str, str],
    depths: Mapping[str, float],
) -> list[DomainEvent]:
    if at.hour != 19:
        return []
    for person, city in sorted(away.items()):
        if depths.get(person, 0.0) < 5.0:
            continue
        missed = [
            e
            for e in surfaced
            if e.payload.get("trigger") == "missing" and e.payload.get("person_id") == person
        ]
        if missed and at - _time(missed[-1]) < MISSING_GAP:
            continue
        if _roll("missing", person, at.date().isoformat()) >= MISSING_CHANCE:
            continue
        name = names.get(person, person.replace("-", " ").title()).split()[0]
        text = (
            f"Missed {name} today. Nearly messaged to see if they fancied a pint before "
            f"remembering they're in {city} now."
        )
        return _surface(None, "missing", text, at, lift=-0.1, person_id=person)
    return []


def _surface(
    memory: DomainEvent | None,
    trigger: str,
    text: str,
    at: datetime,
    *,
    lift: float,
    person_id: str | None = None,
) -> list[DomainEvent]:
    payload: dict[str, object] = {
        "trigger": trigger,
        "text": text,
        "lift": lift,
        "simulated_at": at.isoformat(),
        "owner": "pathos",
    }
    if memory is not None:
        payload["source_memory_id"] = str(memory.event_id)
        if isinstance(memory.payload.get("person_id"), str):
            payload["person_id"] = memory.payload["person_id"]
    if person_id is not None:
        payload["person_id"] = person_id
    event = DomainEvent(
        KIND,
        "pathos",
        payload,
        causation_id=memory.event_id if memory is not None else None,
    )
    recorded = DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "reflection",
            "source": SOURCE,
            "source_event_id": str(event.event_id),
            "owner": "pathos",
            "importance": 0.3,
            "confidence": 1.0,
            **({"person_id": payload["person_id"]} if "person_id" in payload else {}),
        },
        causation_id=event.event_id,
    )
    return [event, recorded]


def lately_on_his_mind(history: Sequence[DomainEvent], at: datetime) -> list[str]:
    """What has come back to him in the last few days."""
    return [
        str(e.payload["text"])
        for e in events_of(history, KIND)[-3:]
        if at - _time(e) <= timedelta(days=3)
    ]


def _gist(memory: DomainEvent) -> str:
    text = " ".join(str(memory.payload["text"]).split())
    first = text.split(". ")[0].rstrip(".")
    return (first if len(first) <= 160 else first[:157].rsplit(" ", 1)[0] + "…") + "."


def _time(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
