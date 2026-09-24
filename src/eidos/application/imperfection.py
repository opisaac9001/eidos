"""The ordinary ways he falls short, and noticing them in himself.

A believable person is not always good. On a tired or low day Patrick sometimes can't face
a plan he made for himself and puts it off. On a restless or lonely evening he ends up on
his phone until gone one and pays for it the next day. When he's exhausted he can be short
with someone over nothing, and, if he cares enough, apologise the next day. None of this is
scheduled: it comes from his energy, mood, sleep, company and follow-through. Each lapse is
lived evidence, so the questions he asks himself can grow out of it ("why do I keep putting
things off?"), and he knows the patterns he'd like to change.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.planning import PlanningState
from eidos.domain.state import PathosState

LATE_NIGHTS_A_WEEK = 2
PATTERNS = {
    "put_off": "putting things off",
    "late_night": "late nights on my phone",
    "snapped": "being short with people when I'm tired",
}


def imperfection_events(
    history: Sequence[DomainEvent],
    at: datetime,
    state: PathosState,
    planning: PlanningState,
    *,
    traits: Mapping[str, float],
    values: Mapping[str, float],
    talking_with: str | None,
    names: Mapping[str, str],
) -> list[DomainEvent]:
    """At most one small failing, or making amends for one, this hour."""
    if not state.awake:
        return []
    return (
        _apologise(history, at, values, names)
        or _snap(history, at, state, talking_with, names)
        or _put_off(history, at, state, planning, traits)
        or _late_night(history, at, state)
    )


def imperfection_context(history: Sequence[DomainEvent], at: datetime) -> list[str]:
    """Patterns he has noticed in himself lately, the ones he'd like to change."""
    recent = [
        str(e.payload.get("pattern"))
        for e in events_of(history, "imperfection.noticed")
        if at - _time(e) <= timedelta(days=30)
    ]
    return [PATTERNS[p] for p in PATTERNS if recent.count(p) >= 2]


# -- putting things off ----------------------------------------------------------------


def _put_off(
    history: Sequence[DomainEvent],
    at: datetime,
    state: PathosState,
    planning: PlanningState,
    traits: Mapping[str, float],
) -> list[DomainEvent]:
    """A plan he made for himself, on a flat day, just doesn't happen."""
    for entry in planning.calendar.values():
        if (
            entry.status != "scheduled"
            or entry.actor_id not in {None, "pathos"}
            or entry.commitment_id is not None
            or entry.companion_id is not None
            or not entry.schedule_id.startswith("pathos-agency-")
        ):
            continue
        starts = datetime.fromisoformat(entry.starts_at)
        # Decided in the hour before, not once it has already begun.
        if not timedelta(0) < starts - at <= timedelta(hours=1):
            continue
        follow_through = float(traits.get("follow_through", 0.64))
        chance = (
            0.04
            + 0.25 * max(0.0, 0.45 - state.energy)
            + 0.15 * max(0.0, -state.valence)
            + 0.2 * max(0.0, 0.64 - follow_through)
        )
        if _roll("put-off", entry.schedule_id) >= chance:
            continue
        before = [
            e
            for e in events_of(history, "imperfection.noticed")
            if e.payload.get("pattern") == "put_off"
        ]
        text = f"Couldn't face '{entry.title.rstrip('.')}' today. " + (
            "Put it off, again. Told myself it doesn't matter." if before else "Put it off."
        )
        noticed = _noticed("put_off", text, at, entry.schedule_id)
        output = [
            noticed,
            DomainEvent(
                "schedule.cancelled",
                "pathos",
                {
                    "schedule_id": entry.schedule_id,
                    "reason": "He put it off; he couldn't face it today.",
                    "simulated_at": at.isoformat(),
                },
                causation_id=noticed.event_id,
                correlation_id=entry.schedule_id,
            ),
        ]
        if entry.intention_id and entry.intention_id in planning.intentions:
            output.append(
                DomainEvent(
                    "intention.abandoned",
                    "pathos",
                    {
                        "intention_id": entry.intention_id,
                        "reason": "Put off for another day.",
                        "simulated_at": at.isoformat(),
                    },
                    causation_id=noticed.event_id,
                    correlation_id=entry.schedule_id,
                )
            )
        return [*output, _memory(noticed, text, at, 0.35)]
    return []


# -- late nights -----------------------------------------------------------------------


def _late_night(
    history: Sequence[DomainEvent], at: datetime, state: PathosState
) -> list[DomainEvent]:
    """On a restless or lonely evening, the phone wins and bedtime slides."""
    if at.hour != 23 or state.location_id != "home":
        return []
    week_ago = at - timedelta(days=7)
    lately = [
        e
        for e in events_of(history, "imperfection.noticed")
        if e.payload.get("pattern") == "late_night" and _time(e) > week_ago
    ]
    if len(lately) >= LATE_NIGHTS_A_WEEK:
        return []
    chance = (
        0.05
        + 0.15 * max(0.0, state.arousal - 0.45)
        + 0.12 * max(0.0, 0.35 - state.connection)
        + 0.08 * max(0.0, -state.valence)
    )
    if _roll("late-night", at.date().isoformat()) >= chance:
        return []
    text = (
        "Ended up scrolling on my phone till gone one. Not one thing I read was worth it. "
        "Going to be wrecked tomorrow."
    )
    noticed = _noticed("late_night", text, at, at.date().isoformat())
    tired = DomainEvent(
        "needs.changed",
        "pathos",
        {
            "rest": round(max(0.0, state.rest - 0.1), 4),
            "reason": "a late night on his phone",
            "simulated_at": at.isoformat(),
        },
        causation_id=noticed.event_id,
    )
    return [noticed, tired, _memory(noticed, text, at, 0.3)]


# -- being short with people -----------------------------------------------------------


def _snap(
    history: Sequence[DomainEvent],
    at: datetime,
    state: PathosState,
    talking_with: str | None,
    names: Mapping[str, str],
) -> list[DomainEvent]:
    """Exhausted, he can be short with someone over nothing."""
    if talking_with is None or talking_with == "user":
        return []
    if state.energy > 0.22 and state.rest > 0.3:
        return []
    if _roll("snap", talking_with, at.isoformat()) >= 0.2:
        return []
    name = names.get(talking_with, talking_with.replace("-", " ").title())
    text = f"Snapped at {name} over nothing. I was just tired. Felt rotten about it straight away."
    noticed = _noticed(
        "snapped", text, at, f"{talking_with}-{at.isoformat()}", person_id=talking_with
    )
    strained = DomainEvent(
        "relationship.changed",
        "pathos",
        {
            "person_id": talking_with,
            "evidence_actor_id": "pathos",
            "tension_delta": 0.08,
            "trust_delta": -0.02,
            "reason": "He was short with them for no good reason.",
            "simulated_at": at.isoformat(),
        },
        causation_id=noticed.event_id,
    )
    return [noticed, strained, _memory(noticed, text, at, 0.45, person_id=talking_with)]


def _apologise(
    history: Sequence[DomainEvent],
    at: datetime,
    values: Mapping[str, float],
    names: Mapping[str, str],
) -> list[DomainEvent]:
    """The next day, if he cares enough, he says sorry."""
    if not 10 <= at.hour <= 19:
        return []
    apologised = {
        str(e.payload.get("snap_id")) for e in events_of(history, "imperfection.apologised")
    }
    for snap in events_of(history, "imperfection.noticed"):
        if snap.payload.get("pattern") != "snapped" or str(snap.event_id) in apologised:
            continue
        waited = at - _time(snap)
        if not timedelta(hours=12) <= waited <= timedelta(days=3):
            continue
        care = float(values.get("care", 0.78))
        if _roll("apologise", str(snap.event_id), at.isoformat()) >= 0.08 + 0.12 * care:
            continue
        person = str(snap.payload.get("person_id"))
        name = names.get(person, person.replace("-", " ").title())
        text = f"Said sorry to {name} for snapping yesterday. They said they hadn't even noticed, which was kind."
        apology = DomainEvent(
            "imperfection.apologised",
            "pathos",
            {
                "snap_id": str(snap.event_id),
                "person_id": person,
                "text": text,
                "simulated_at": at.isoformat(),
                "owner": "pathos",
            },
            causation_id=snap.event_id,
        )
        eased = DomainEvent(
            "relationship.changed",
            "pathos",
            {
                "person_id": person,
                "evidence_actor_id": "pathos",
                "tension_delta": -0.07,
                "trust_delta": 0.03,
                "reason": "He apologised for being short.",
                "simulated_at": at.isoformat(),
            },
            causation_id=apology.event_id,
        )
        return [apology, eased, _memory(apology, text, at, 0.45, person_id=person)]
    return []


# -- helpers ---------------------------------------------------------------------------


def _noticed(
    pattern: str, text: str, at: datetime, key: str, *, person_id: str | None = None
) -> DomainEvent:
    return DomainEvent(
        "imperfection.noticed",
        "pathos",
        {
            "pattern": pattern,
            "key": key,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
            **({"person_id": person_id} if person_id else {}),
        },
        correlation_id=f"imperfection-{pattern}-{key}",
    )


def _memory(
    source: DomainEvent,
    text: str,
    at: datetime,
    importance: float,
    *,
    person_id: str | None = None,
) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "experience",
            "source": "lived-imperfection",
            "source_event_id": str(source.event_id),
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
            **({"person_id": person_id} if person_id else {}),
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _time(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))
