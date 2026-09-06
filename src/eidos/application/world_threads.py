"""Advance bounded consequences from accepted neighborhood events."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.world_threads import WorldThread, project_world_threads


def world_thread_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actor_locations: Mapping[str, str],
) -> list[DomainEvent]:
    """Open, advance, and close event aftermath without granting actors omniscience."""
    if simulated_at.utcoffset() is None:
        raise ValueError("World thread time must be timezone-aware")
    output: list[DomainEvent] = []
    state = project_world_threads(history)
    opened_sources = {thread.source_event_id for thread in state.values()}
    for occurred in history:
        if occurred.kind != "world_event.occurred" or str(occurred.event_id) in opened_sources:
            continue
        occurred_at = _event_time(occurred)
        duration = occurred.payload.get("duration_hours")
        metadata = [
            occurred.payload.get("proposal_id"),
            occurred.payload.get("event_type"),
            occurred.payload.get("description"),
            occurred.payload.get("location_id"),
            occurred.payload.get("theme"),
        ]
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not 1 <= float(duration) <= 24
            or not all(isinstance(value, str) and value.strip() for value in metadata)
            or simulated_at - occurred_at > timedelta(hours=1)
        ):
            continue
        thread_id = f"world-thread-{occurred.payload['proposal_id']}"
        opened = DomainEvent(
            "world_thread.opened",
            "pathos",
            {
                "thread_id": thread_id,
                "source_event_id": str(occurred.event_id),
                "event_type": str(occurred.payload["event_type"]),
                "location_id": str(occurred.payload["location_id"]),
                "theme": str(occurred.payload["theme"]),
                "summary": str(occurred.payload["description"]),
                "started_at": occurred_at.isoformat(),
                "due_at": (occurred_at + timedelta(hours=float(duration))).isoformat(),
                "simulated_at": simulated_at.isoformat(),
                "visibility": "world",
            },
            causation_id=occurred.event_id,
            correlation_id=thread_id,
        )
        output.append(opened)
        state = project_world_threads([*history, *output])
    for thread in list(state.values()):
        if thread.status != "active":
            continue
        due_at = datetime.fromisoformat(thread.due_at)
        started_at = datetime.fromisoformat(thread.started_at)
        now_history = [*history, *output]
        if thread.stage == 1 and simulated_at >= started_at + (due_at - started_at) / 2:
            progressed = _transition(
                "world_thread.progressed",
                thread,
                simulated_at,
                f"The {thread.event_type.replace('_', ' ')} is still unfolding; its {thread.theme} theme remains visible.",
                now_history,
            )
            output.extend(_with_observations(progressed, thread, actor_locations, simulated_at))
            state = project_world_threads([*history, *output])
            thread = state[thread.thread_id]
            now_history = [*history, *output]
        if simulated_at < datetime.fromisoformat(thread.due_at):
            continue
        if thread.extension_count == 0 and _sample(thread.thread_id) < 0.34:
            extended = DomainEvent(
                "world_thread.extended",
                "pathos",
                {
                    "thread_id": thread.thread_id,
                    "prior_due_at": thread.due_at,
                    "due_at": (
                        datetime.fromisoformat(thread.due_at) + timedelta(days=2)
                    ).isoformat(),
                    "summary": f"The {thread.event_type.replace('_', ' ')} has prompted neighbors to continue for two more days.",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=_latest_transition(now_history, thread.thread_id).event_id,
                correlation_id=thread.thread_id,
            )
            output.extend(_with_observations(extended, thread, actor_locations, simulated_at))
        else:
            outcomes = (
                "settled quietly",
                "left an open question in the neighborhood",
                "ended with a modest shared result",
            )
            outcome = outcomes[int(_sample(f"outcome-{thread.thread_id}") * len(outcomes))]
            resolved = DomainEvent(
                "world_thread.resolved",
                "pathos",
                {
                    "thread_id": thread.thread_id,
                    "outcome": outcome,
                    "summary": f"The {thread.event_type.replace('_', ' ')} {outcome}.",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=_latest_transition(now_history, thread.thread_id).event_id,
                correlation_id=thread.thread_id,
            )
            output.extend(_with_observations(resolved, thread, actor_locations, simulated_at))
    return output


def _transition(
    kind: str,
    thread: WorldThread,
    simulated_at: datetime,
    summary: str,
    history: Sequence[DomainEvent],
) -> DomainEvent:
    return DomainEvent(
        kind,
        "pathos",
        {
            "thread_id": thread.thread_id,
            "summary": summary,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=_latest_transition(history, thread.thread_id).event_id,
        correlation_id=thread.thread_id,
    )


def _with_observations(
    transition: DomainEvent,
    thread: WorldThread,
    actor_locations: Mapping[str, str],
    simulated_at: datetime,
) -> list[DomainEvent]:
    output = [transition]
    for actor_id, location_id in sorted(actor_locations.items()):
        if location_id != thread.location_id:
            continue
        perception = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": actor_id,
                "source_event_id": str(transition.event_id),
                "source_kind": "world_thread",
                "text": str(transition.payload["summary"]),
                "privacy": "public",
                "location_id": location_id,
                "reported": False,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=transition.event_id,
            correlation_id=thread.thread_id,
        )
        output.append(perception)
        if actor_id == "pathos":
            output.append(
                DomainEvent(
                    "memory.recorded",
                    "pathos",
                    {
                        "text": str(transition.payload["summary"]),
                        "owner": "pathos",
                        "category": "world-thread",
                        "source": "direct-perception",
                        "source_event_id": str(perception.event_id),
                        "location_id": location_id,
                        "importance": 0.35,
                        "confidence": 1.0,
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=perception.event_id,
                    correlation_id=thread.thread_id,
                )
            )
    return output


def _latest_transition(history: Sequence[DomainEvent], thread_id: str) -> DomainEvent:
    return next(
        event
        for event in reversed(history)
        if event.kind.startswith("world_thread.") and event.payload.get("thread_id") == thread_id
    )


def _event_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if not isinstance(value, str):
        raise ValueError("Occurred world event needs simulated time")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Occurred world event time must be timezone-aware")
    return parsed


def _sample(key: str) -> float:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
