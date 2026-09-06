"""Replayable neighborhood threads that outlive an event's opening moment."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class WorldThread:
    thread_id: str
    source_event_id: str
    event_type: str
    location_id: str
    theme: str
    status: str
    stage: int
    started_at: str
    due_at: str
    summary: str
    extension_count: int = 0
    outcome: str | None = None


def project_world_threads(history: Sequence[DomainEvent]) -> dict[str, WorldThread]:
    threads: dict[str, WorldThread] = {}
    latest_transition: dict[str, str] = {}
    seen: dict[str, DomainEvent] = {}
    for event in history:
        if event.kind == "world_thread.opened":
            thread_id = _required(event, "thread_id")
            source_id = _required(event, "source_event_id")
            source = seen.get(source_id)
            if thread_id in threads:
                raise ValueError("World thread already exists")
            if source is None or source.kind != "world_event.occurred":
                raise ValueError("World thread must cite an occurred world event")
            if event.causation_id != source.event_id:
                raise ValueError("World thread opening must be caused by its source")
            if any(
                _required(event, key) != _required(source, source_key)
                for key, source_key in (
                    ("event_type", "event_type"),
                    ("location_id", "location_id"),
                    ("theme", "theme"),
                )
            ):
                raise ValueError("World thread opening must preserve source facts")
            started_at = _time(event, "started_at")
            due_at = _time(event, "due_at")
            if due_at <= started_at:
                raise ValueError("World thread due time must follow its start")
            threads[thread_id] = WorldThread(
                thread_id,
                source_id,
                _required(event, "event_type"),
                _required(event, "location_id"),
                _required(event, "theme"),
                "active",
                1,
                started_at.isoformat(),
                due_at.isoformat(),
                _required(event, "summary"),
            )
            latest_transition[thread_id] = str(event.event_id)
        elif event.kind == "world_thread.progressed":
            thread_id = _required(event, "thread_id")
            thread = threads.get(thread_id)
            if thread is None or thread.status != "active" or thread.stage != 1:
                raise ValueError("Only a newly active world thread can progress")
            _require_causal_transition(event, thread_id, latest_transition)
            changed_at = _time(event, "simulated_at")
            midpoint = (
                datetime.fromisoformat(thread.started_at)
                + (
                    datetime.fromisoformat(thread.due_at)
                    - datetime.fromisoformat(thread.started_at)
                )
                / 2
            )
            if changed_at < midpoint:
                raise ValueError("World thread cannot progress before its midpoint")
            threads[thread_id] = replace(thread, stage=2, summary=_required(event, "summary"))
            latest_transition[thread_id] = str(event.event_id)
        elif event.kind == "world_thread.extended":
            thread_id = _required(event, "thread_id")
            thread = threads.get(thread_id)
            prior_due = _time(event, "prior_due_at")
            next_due = _time(event, "due_at")
            if (
                thread is None
                or thread.status != "active"
                or thread.extension_count != 0
                or prior_due.isoformat() != thread.due_at
                or next_due <= prior_due
            ):
                raise ValueError("World thread extension is stale or invalid")
            _require_causal_transition(event, thread_id, latest_transition)
            if _time(event, "simulated_at") < prior_due:
                raise ValueError("World thread cannot extend before it is due")
            threads[thread_id] = replace(
                thread,
                stage=3,
                due_at=next_due.isoformat(),
                extension_count=1,
                summary=_required(event, "summary"),
            )
            latest_transition[thread_id] = str(event.event_id)
        elif event.kind == "world_thread.resolved":
            thread_id = _required(event, "thread_id")
            thread = threads.get(thread_id)
            if thread is None or thread.status != "active":
                raise ValueError("Only an active world thread can resolve")
            _require_causal_transition(event, thread_id, latest_transition)
            if _time(event, "simulated_at") < datetime.fromisoformat(thread.due_at):
                raise ValueError("World thread cannot resolve before it is due")
            threads[thread_id] = replace(
                thread,
                status="resolved",
                stage=4,
                summary=_required(event, "summary"),
                outcome=_required(event, "outcome"),
            )
            latest_transition[thread_id] = str(event.event_id)
        seen[str(event.event_id)] = event
    return threads


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _time(event: DomainEvent, key: str) -> datetime:
    parsed = datetime.fromisoformat(_required(event, key))
    if parsed.utcoffset() is None:
        raise ValueError("World thread times must be timezone-aware")
    return parsed


def _require_causal_transition(
    event: DomainEvent, thread_id: str, latest_transition: dict[str, str]
) -> None:
    cause = event.causation_id
    if cause is None or str(cause) != latest_transition.get(thread_id):
        raise ValueError("World thread transition must cite its prior stage")
