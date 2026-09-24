"""Availability and replay-stable response timing for user communication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.application.deliveries import active_delivery
from eidos.application.urgent_incidents import active_incident_location
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.planning import PlanningState, project_planning
from eidos.domain.routine import beats_between
from eidos.domain.scenes import project_scenes
from eidos.domain.state import PathosState
from eidos.domain.wellbeing import project_wellbeing


@dataclass(frozen=True, slots=True)
class CommunicationAvailability:
    status: str
    reason: str
    can_visit: bool
    hurried: bool
    next_commitment_at: str | None = None
    next_commitment_title: str | None = None


def communication_availability(
    history: Sequence[DomainEvent], state: PathosState
) -> CommunicationAvailability:
    if not state.awake:
        return CommunicationAvailability("asleep", "He is asleep.", False, False)
    if state.location_id == "in_transit":
        return CommunicationAvailability(
            "travelling",
            "He is on his way somewhere. A message can wait for him; he cannot sit down for a visit yet.",
            False,
            True,
        )
    closed_calls = {e.payload.get("call_id") for e in events_of(history, "phone.call_completed")}
    if any(
        e.payload.get("call_id") not in closed_calls
        for e in events_of(history, "phone.call_answered")
    ):
        interrupted = any(
            s.status == "paused" and {s.initiator_id, s.partner_id} == {"pathos", "user"}
            for s in project_scenes(history).scenes.values()
        )
        return CommunicationAvailability(
            "interrupted" if interrupted else "occupied", "He is on a phone call.", False, False
        )
    planning = project_planning(list(history))
    upcoming_at, upcoming_title = _next_commitment(state, planning)
    minutes_until = (
        (upcoming_at - state.simulated_at).total_seconds() / 60 if upcoming_at is not None else None
    )
    hurried = minutes_until is not None and minutes_until <= 60
    rounded_minutes = max(1, round(minutes_until)) if minutes_until is not None else None
    timing = (
        f" He has about {rounded_minutes} minute{'s' if rounded_minutes != 1 else ''} "
        "before he needs to head out."
        if hurried and rounded_minutes is not None and upcoming_title is not None
        else ""
    )
    timing_fields = (
        upcoming_at.isoformat() if upcoming_at is not None else None,
        upcoming_title,
    )
    scenes = project_scenes(history).scenes.values()
    if any(
        scene.status == "paused" and {scene.initiator_id, scene.partner_id} == {"pathos", "user"}
        for scene in scenes
    ):
        return CommunicationAvailability(
            "interrupted", "The conversation is paused by something happening now.", False, False
        )
    if any(
        scene.status == "active" and {scene.initiator_id, scene.partner_id} == {"pathos", "user"}
        for scene in scenes
    ):
        return CommunicationAvailability(
            "in_conversation",
            f"You are spending time together now.{timing}",
            True,
            hurried,
            *timing_fields,
        )
    if any(
        scene.status == "active" and "pathos" in {scene.initiator_id, scene.partner_id}
        for scene in scenes
    ):
        return CommunicationAvailability("occupied", "He is already with someone.", False, False)
    departed_visits = {
        str(event.payload["visit_id"]) for event in events_of(history, "visitor.departed")
    }
    if any(
        str(event.payload["visit_id"]) not in departed_visits
        for event in events_of(history, "visitor.admitted")
    ):
        return CommunicationAvailability(
            "occupied", "He has someone visiting at home.", False, False
        )
    if active_delivery(history) is not None:
        return CommunicationAvailability(
            "occupied", "He is answering a delivery at the door.", False, False
        )
    if active_incident_location(history, state.simulated_at) is not None:
        return CommunicationAvailability(
            "occupied", "He is responding to something nearby.", False, False
        )
    now = state.simulated_at
    if any(
        item.status == "scheduled"
        and datetime.fromisoformat(item.starts_at) <= now
        and (item.ends_at is None or now < datetime.fromisoformat(item.ends_at))
        for item in planning.calendar.values()
    ):
        return CommunicationAvailability(
            "occupied", "He is in the middle of something he planned.", False, False
        )
    physical = project_wellbeing(history).active
    if physical is not None and physical.severity >= 0.45:
        return CommunicationAvailability(
            "unwell",
            f"He is awake but resting with {physical.kind.replace('_', ' ')}.",
            False,
            hurried,
            *timing_fields,
        )
    if physical is not None and physical.severity >= 0.3:
        return CommunicationAvailability(
            "recovering",
            f"He is taking things slowly with {physical.kind.replace('_', ' ')}.",
            True,
            True,
            *timing_fields,
        )
    if state.energy < 0.25:
        return CommunicationAvailability(
            "tired", "He is awake, but does not have much energy for company.", False, hurried
        )
    if hurried:
        return CommunicationAvailability(
            "hurried",
            f"He is free briefly.{timing}",
            True,
            True,
            *timing_fields,
        )
    return CommunicationAvailability(
        "available", "He has room for company.", True, False, *timing_fields
    )


def _next_commitment(
    state: PathosState, planning: PlanningState
) -> tuple[datetime | None, str | None]:
    planned = [
        (datetime.fromisoformat(item.starts_at), item.title)
        for item in planning.calendar.values()
        if item.status == "scheduled"
        and datetime.fromisoformat(item.starts_at) > state.simulated_at
    ]
    routine = [
        (at, beat.description.rstrip("."))
        for at, beat in beats_between(state.simulated_at, state.simulated_at + timedelta(hours=24))
        if beat.location_id != state.location_id
    ]
    return min(
        [*planned, *routine], default=(None, None), key=lambda item: item[0] or state.simulated_at
    )


def reply_due_at(history: Sequence[DomainEvent], state: PathosState, request_id: str) -> datetime:
    """Choose a deterministic delay so replay/restart never rerolls responsiveness."""
    if not state.awake:
        tomorrow = state.simulated_at + timedelta(days=1)
        return tomorrow.replace(hour=7, minute=0, second=0, microsecond=0)
    availability = communication_availability(history, state)
    choices = (5, 15, 30, 60)
    seed = f"{request_id}:{state.simulated_at.date().isoformat()}"
    minutes = choices[int(sha256(seed.encode()).hexdigest()[:8], 16) % len(choices)]
    if availability.status in {"occupied", "unwell"}:
        minutes = max(minutes, 60)
    elif availability.status in {"recovering", "tired", "hurried"}:
        minutes = max(minutes, 30)
    return state.simulated_at + timedelta(minutes=minutes)
