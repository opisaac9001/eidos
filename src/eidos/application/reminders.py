"""Remembering what he's got on: naturally, and with a reminder on his phone when it matters.

People don't keep their diary in their heads. A plan comes back to mind when the day comes
round, when they scroll their phone, when they pass the place or see the person; and for
the things that matter and are a few days off (a plan with a friend, a funeral, a class)
they set a reminder, more or less reliably depending on how organised they are.

- ``reminder.set``: he put it in his phone when he made the plan.
- ``reminder.fired``: the phone buzzed (not while he's asleep or it's dead), and he
  remembers it did.
- ``plan.noticed``: it crossed his mind on its own: scrolling his phone, or the morning
  of. These count as rehearsal; a plan rehearsed lately can't slip his mind
  (``scheduled_activity.prospective_memory_lapse``).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.application.bookings import remember
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.planning import CalendarEntry, PlanningState

SET = "reminder.set"
FIRED = "reminder.fired"
MISSED = "reminder.missed"
NOTICED = "plan.noticed"
# Plans his life books for him that need no reminder: shifts, his own work sessions, the
# small doings of an hour.
_NO_REMINDER = ("doing-", "work-rota-", "freelance-", "workshop-drop-in-")
# How far ahead a plan has to be before he'd bother with a reminder.
AHEAD = timedelta(days=2)
REHEARSED_WITHIN = timedelta(hours=48)


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _at(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return None


def _matters(entry: CalendarEntry) -> bool:
    if entry.schedule_id.startswith(_NO_REMINDER):
        return False
    if entry.companion_id or entry.commitment_id:
        return True
    title = entry.title.casefold()
    return any(w in title for w in ("funeral", "class", "appointment", "dentist", "doctor"))


def _clock(at: datetime) -> str:
    hour = at.hour % 12 or 12
    return f"{hour}:{at.minute:02d}" if at.minute else f"{hour}"


def reminder_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    planning: PlanningState,
    follow_through: float,
    awake: bool,
    phone_dead: bool,
    scrolling: bool,
) -> list[DomainEvent]:
    """This hour: reminders set for new plans, ones that fire, and plans that cross his mind."""
    output: list[DomainEvent] = []
    set_for = {str(e.payload.get("schedule_id")) for e in events_of(history, SET)}
    settled = {str(e.payload.get("schedule_id")) for e in events_of(history, FIRED, MISSED)}
    made_lately = {
        str(e.payload.get("schedule_id")): when
        for e in events_of(history, "schedule.created")[-80:]
        if (when := _at(e)) is not None and at - when <= timedelta(hours=2)
    }
    noticed_lately = {
        str(e.payload.get("schedule_id"))
        for e in events_of(history, NOTICED, FIRED)[-80:]
        if (when := _at(e)) is not None and at - when <= timedelta(hours=24)
    }
    for entry in sorted(planning.calendar.values(), key=lambda e: e.starts_at):
        if entry.status != "scheduled" or entry.actor_id not in {None, "pathos"}:
            continue
        starts = datetime.fromisoformat(entry.starts_at)
        if starts <= at:
            continue
        # Setting one, just after making the plan, when it matters and is days off.
        if (
            entry.schedule_id in made_lately
            and entry.schedule_id not in set_for
            and awake
            and _matters(entry)
            and starts - at >= AHEAD
            and _roll("set", entry.schedule_id) < 0.3 + 0.6 * follow_through
        ):
            fires_at = starts - timedelta(hours=2)
            if fires_at.hour < 9:
                fires_at = fires_at.replace(hour=9, minute=0)
            decided = DomainEvent(
                SET,
                "pathos",
                {
                    "schedule_id": entry.schedule_id,
                    "title": entry.title,
                    "fires_at": fires_at.isoformat(),
                    "simulated_at": at.isoformat(),
                },
                correlation_id=entry.schedule_id,
            )
            output += [
                decided,
                remember(
                    decided,
                    f"Put a reminder in my phone: {entry.title}, {starts:%A}.",
                    at,
                    0.2,
                    origin="lived-reminder",
                    category="experience",
                ),
            ]
            set_for.add(entry.schedule_id)
        # It crossing his mind on its own.
        if (
            awake
            and entry.schedule_id not in noticed_lately
            and not entry.schedule_id.startswith(_NO_REMINDER)
            and (
                (scrolling and starts - at <= timedelta(hours=48))
                or (at.hour == 9 and starts.date() == at.date())
            )
        ):
            output.append(
                DomainEvent(
                    NOTICED,
                    "pathos",
                    {
                        "schedule_id": entry.schedule_id,
                        "how": "scrolling his phone" if scrolling else "the day came round",
                        "simulated_at": at.isoformat(),
                    },
                    correlation_id=entry.schedule_id,
                )
            )
            noticed_lately.add(entry.schedule_id)
    # Reminders firing.
    for event in events_of(history, SET)[-60:]:
        schedule_id = str(event.payload.get("schedule_id"))
        if schedule_id in settled:
            continue
        booked = planning.calendar.get(schedule_id)
        if booked is None or booked.status != "scheduled":
            continue
        fires_at = datetime.fromisoformat(str(event.payload.get("fires_at")))
        starts = datetime.fromisoformat(booked.starts_at)
        if at < fires_at:
            continue
        if awake and not phone_dead:
            fired = DomainEvent(
                FIRED,
                "pathos",
                {"schedule_id": schedule_id, "simulated_at": at.isoformat()},
                causation_id=event.event_id,
                correlation_id=schedule_id,
            )
            output += [
                fired,
                remember(
                    fired,
                    f"Phone buzzed: {booked.title}, {_clock(starts)}.",
                    at,
                    0.3,
                    origin="lived-reminder",
                    category="experience",
                ),
            ]
            settled.add(schedule_id)
        elif at >= starts:
            output.append(
                DomainEvent(
                    MISSED,
                    "pathos",
                    {
                        "schedule_id": schedule_id,
                        "reason": "phone dead" if phone_dead else "asleep",
                        "simulated_at": at.isoformat(),
                    },
                    causation_id=event.event_id,
                    correlation_id=schedule_id,
                )
            )
            settled.add(schedule_id)
    return output


def reminded(history: Sequence[DomainEvent], schedule_id: str) -> bool:
    """He put it in his phone: it'll buzz, and it won't slip his mind."""
    return any(e.payload.get("schedule_id") == schedule_id for e in events_of(history, SET))


def rehearsed_lately(history: Sequence[DomainEvent], schedule_id: str, at: datetime) -> bool:
    """It has crossed his mind in the last couple of days: a reminder, scrolling past it,
    the day coming round, or his own mind running ahead to it."""
    for event in events_of(history, FIRED, NOTICED, "mind.layer_pulsed")[-400:]:
        if event.kind == "mind.layer_pulsed" and (
            event.payload.get("layer") != "prospective"
            or event.payload.get("focus_id") != schedule_id
        ):
            continue
        if event.kind != "mind.layer_pulsed" and event.payload.get("schedule_id") != schedule_id:
            continue
        when = _at(event)
        if when is not None and timedelta(0) <= at - when <= REHEARSED_WITHIN:
            return True
    return False


def made_at(history: Sequence[DomainEvent], schedule_id: str) -> datetime | None:
    """When the plan went in the diary."""
    for event in reversed(events_of(history, "schedule.created")):
        if event.payload.get("schedule_id") == schedule_id:
            return _at(event)
    return None
