"""Bounded, explicit catch-up previews and restart-safe session projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.routine import beats_between


@dataclass(frozen=True, slots=True)
class CatchUpPreview:
    starts_at: str
    ends_at: str
    hours: float
    chunks: int
    routine_beats: int
    due_commitments: int
    scheduled_items: int


@dataclass(frozen=True, slots=True)
class CatchUpSession:
    catch_up_id: str
    starts_at: str
    target_at: str
    status: str
    start_event_id: str


def preview_catch_up(
    history: Sequence[DomainEvent], starts_at: datetime, hours: float
) -> CatchUpPreview:
    _validate_hours(hours)
    ends_at = starts_at + timedelta(hours=hours)
    planning = project_planning(list(history))
    due = sum(
        item.status == "active" and starts_at < datetime.fromisoformat(item.due_at) <= ends_at
        for item in planning.commitments.values()
    )
    scheduled = sum(
        item.status == "scheduled" and starts_at < datetime.fromisoformat(item.starts_at) <= ends_at
        for item in planning.calendar.values()
    )
    return CatchUpPreview(
        starts_at.isoformat(),
        ends_at.isoformat(),
        float(hours),
        int((hours + 23.999999) // 24),
        len(beats_between(starts_at, ends_at)),
        due,
        scheduled,
    )


def active_catch_up(history: Sequence[DomainEvent]) -> CatchUpSession | None:
    sessions: dict[str, CatchUpSession] = {}
    for event in history:
        if event.kind == "catch_up.started":
            catch_up_id = str(event.payload["catch_up_id"])
            sessions[catch_up_id] = CatchUpSession(
                catch_up_id,
                str(event.payload["starts_at"]),
                str(event.payload["target_at"]),
                "active",
                str(event.event_id),
            )
        elif event.kind == "catch_up.completed":
            catch_up_id = str(event.payload["catch_up_id"])
            session = sessions.get(catch_up_id)
            if session is None or session.status != "active":
                raise ValueError("Catch-up completion has no active session")
            sessions[catch_up_id] = CatchUpSession(
                session.catch_up_id,
                session.starts_at,
                session.target_at,
                "completed",
                session.start_event_id,
            )
    active = [session for session in sessions.values() if session.status == "active"]
    if len(active) > 1:
        raise ValueError("Only one catch-up session may be active")
    return active[0] if active else None


def _validate_hours(hours: float) -> None:
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not 0 < hours <= 168:
        raise ValueError("Catch-up must be greater than zero and at most 168 hours")
