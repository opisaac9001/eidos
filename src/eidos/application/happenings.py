"""Small things that happen to him, because of where he is and what he's doing.

Not dice rolled at fixed hours: the world acting on his actual situation, the way a game
master would (Concordia's idea of a referee for what happens). He gets caught in the rain
because he went out in it; the bus is late on the morning he's cutting it fine; he can't
find his keys when he's leaving tired; the chisel slips at the bench; his phone dies after
an evening of messages, and he misses the group chat for a while. They're rare, fit the
moment, have consequences (a sore thumb throbs for hours; a dead phone can't be read), and
become memories.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.application.bookings import remember
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

HAPPENED = "happening.occurred"
PER_DAY = 2


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _at(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return None


def phone_dead(history: Sequence[DomainEvent], at: datetime) -> bool:
    """His phone died and he hasn't got it charged again yet."""
    for event in reversed(events_of(history, HAPPENED)[-6:]):
        if event.payload.get("kind") == "phone_died":
            until = event.payload.get("until")
            return isinstance(until, str) and at < datetime.fromisoformat(until)
    return False


def happening_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    location_id: str,
    weather: str | None,
    alertness: float,
    at_work: bool,
    next_commitment: datetime | None,
) -> list[DomainEvent]:
    """At most one small happening this hour, when the moment calls for one."""
    if not awake:
        return []
    today = [
        e
        for e in events_of(history, HAPPENED)[-6:]
        if (when := _at(e)) and when.date() == at.date()
    ]
    if len(today) >= PER_DAY:
        return []
    kinds_today = {e.payload.get("kind") for e in today}
    hour = at.isoformat()[:13]
    travelled = [
        e
        for e in events_of(history, "pathos.travel_started")[-3:]
        if (when := _at(e)) and timedelta(0) <= at - when <= timedelta(hours=1)
    ]
    candidates: list[tuple[str, float, str, float, dict[str, object]]] = []
    if travelled and weather == "Light rain":
        candidates.append(
            ("caught_in_rain", 0.5, "Got caught in the rain on the way. Soaked through.", -0.2, {})
        )
    if (
        travelled
        and next_commitment is not None
        and timedelta(0) <= next_commitment - at <= timedelta(minutes=40)
    ):
        candidates.append(
            (
                "cutting_it_fine",
                0.12,
                "Cut it fine. Had to run the last bit, made it just.",
                -0.1,
                {},
            )
        )
    if travelled and alertness < 0.75 and at.hour <= 11:
        candidates.append(
            (
                "lost_keys",
                0.15,
                "Couldn't find my keys for ten minutes. They were in my coat.",
                -0.1,
                {},
            )
        )
    if at_work and location_id == "workshop":
        candidates.append(
            (
                "nicked_thumb",
                0.03,
                "Chisel slipped and caught my thumb. Stupid. It's throbbing.",
                -0.2,
                {},
            )
        )
    messages_today = sum(
        1
        for e in events_of(
            history, "chat.message", "contact.reached_out", "contact.reply_received"
        )[-40:]
        if (when := _at(e)) and when.date() == at.date()
    )
    if messages_today >= 8 and 19 <= at.hour <= 22:
        candidates.append(
            ("phone_died", 0.3, "Phone died on me. Didn't notice for a while.", -0.05,
             {"until": (at + timedelta(hours=2)).isoformat()})
        )  # fmt: skip
    if location_id == "home" and 9 <= at.hour <= 18 and at.weekday() < 6:
        candidates.append(
            (
                "parcel_next_door",
                0.02,
                "Card through the door: they left a parcel with next door.",
                -0.05,
                {},
            )
        )
        candidates.append(
            (
                "knock_at_door",
                0.02,
                "Someone knocked collecting for the church roof. Gave them a quid.",
                0.0,
                {},
            )
        )
    for kind, chance, text, tone, extra in candidates:
        if kind in kinds_today or _roll(kind, hour) >= chance:
            continue
        happened = DomainEvent(
            HAPPENED,
            "pathos",
            {"kind": kind, "text": text, "tone": tone, "simulated_at": at.isoformat(), **extra},
        )
        return [
            happened,
            remember(happened, text, at, 0.3, origin="lived-happening", category="experience"),
        ]
    return []
