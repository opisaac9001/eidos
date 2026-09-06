"""Availability and replay-stable response timing for user communication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.application.deliveries import active_delivery
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.scenes import project_scenes
from eidos.domain.state import PathosState


@dataclass(frozen=True, slots=True)
class CommunicationAvailability:
    status: str
    reason: str
    can_visit: bool
    hurried: bool


def communication_availability(
    history: Sequence[DomainEvent], state: PathosState
) -> CommunicationAvailability:
    if not state.awake:
        return CommunicationAvailability("asleep", "He is asleep.", False, False)
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
            "in_conversation", "You are spending time together now.", True, False
        )
    if any(
        scene.status == "active" and "pathos" in {scene.initiator_id, scene.partner_id}
        for scene in scenes
    ):
        return CommunicationAvailability("occupied", "He is already with someone.", False, False)
    departed_visits = {
        str(event.payload["visit_id"]) for event in history if event.kind == "visitor.departed"
    }
    if any(
        event.kind == "visitor.admitted" and str(event.payload["visit_id"]) not in departed_visits
        for event in history
    ):
        return CommunicationAvailability(
            "occupied", "He has someone visiting at home.", False, False
        )
    if active_delivery(history) is not None:
        return CommunicationAvailability(
            "occupied", "He is answering a delivery at the door.", False, False
        )
    planning = project_planning(list(history))
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
    next_start = min(
        (
            datetime.fromisoformat(item.starts_at)
            for item in planning.calendar.values()
            if item.status == "scheduled" and datetime.fromisoformat(item.starts_at) > now
        ),
        default=None,
    )
    hurried = next_start is not None and next_start <= now + timedelta(hours=1)
    if state.energy < 0.25:
        return CommunicationAvailability(
            "tired", "He is awake, but does not have much energy for company.", False, hurried
        )
    if hurried:
        return CommunicationAvailability(
            "hurried", "He is free briefly, with something else coming up.", True, True
        )
    return CommunicationAvailability("available", "He has room for company.", True, False)


def reply_due_at(history: Sequence[DomainEvent], state: PathosState, request_id: str) -> datetime:
    """Choose a deterministic delay so replay/restart never rerolls responsiveness."""
    if not state.awake:
        tomorrow = state.simulated_at + timedelta(days=1)
        return tomorrow.replace(hour=7, minute=0, second=0, microsecond=0)
    availability = communication_availability(history, state)
    choices = (5, 15, 30, 60)
    seed = f"{request_id}:{state.simulated_at.date().isoformat()}"
    minutes = choices[int(sha256(seed.encode()).hexdigest()[:8], 16) % len(choices)]
    if availability.status == "occupied":
        minutes = max(minutes, 60)
    elif availability.status in {"tired", "hurried"}:
        minutes = max(minutes, 30)
    return state.simulated_at + timedelta(minutes=minutes)
