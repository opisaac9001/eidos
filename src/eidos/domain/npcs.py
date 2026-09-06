"""Replayable low-detail state for non-player people living offscreen."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from types import MappingProxyType
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.world import PEOPLE, npc_location


@dataclass(frozen=True, slots=True)
class NPCState:
    actor_id: str
    location_id: str = "home"
    usual_location_id: str = "home"
    energy: float = 0.7
    connection: float = 0.5
    purpose: float = 0.5
    private_activity: str = "unrecorded"
    goal_id: str | None = None
    goal_title: str | None = None
    goal_motivation: str | None = None
    goal_status: str | None = None
    plan_id: str | None = None
    plan_title: str | None = None
    plan_motivation: str | None = None
    plan_need: str | None = None
    plan_goal_id: str | None = None
    plan_action: str | None = None
    plan_location_id: str | None = None
    plan_scheduled_for: datetime | None = None
    plan_due_at: datetime | None = None
    plan_status: str | None = None


@dataclass(frozen=True, slots=True)
class NPCWorldState:
    people: Mapping[str, NPCState]

    def __post_init__(self) -> None:
        object.__setattr__(self, "people", MappingProxyType(dict(self.people)))

    def apply(self, event: DomainEvent) -> NPCWorldState:
        people = dict(self.people)
        if event.kind == "world.person_registered":
            introduced_id = _required(event, "entity_id")
            if introduced_id in people:
                raise ValueError("Registered world person already exists in NPC state")
            people[introduced_id] = NPCState(
                actor_id=introduced_id,
                location_id="home",
                usual_location_id=_required(event, "location_id"),
            )
            return NPCWorldState(people)
        actor_id = event.payload.get("actor_id")
        if not isinstance(actor_id, str) or actor_id not in people:
            return self
        person = people[actor_id]
        if event.kind == "npc.moved":
            location_id = _required(event, "location_id")
            people[actor_id] = replace(person, location_id=location_id)
        elif event.kind == "npc.activity_recorded":
            people[actor_id] = replace(person, private_activity=_required(event, "activity"))
        elif event.kind == "npc.needs_changed":
            people[actor_id] = replace(
                person,
                energy=_bounded(event, "energy"),
                connection=_bounded(event, "connection"),
                purpose=_bounded(event, "purpose"),
            )
        elif event.kind == "npc.goal_formed":
            if person.goal_status == "active":
                raise ValueError("NPC already has an active goal")
            if (
                event.payload.get("owner") != actor_id
                or event.payload.get("visibility") != "private"
            ):
                raise ValueError("NPC goals must remain private to their owner")
            people[actor_id] = replace(
                person,
                goal_id=_required(event, "goal_id"),
                goal_title=_required(event, "title"),
                goal_motivation=_required(event, "motivation"),
                goal_status="active",
            )
        elif event.kind == "npc.plan_created":
            if person.plan_status == "active":
                raise ValueError("NPC already has an active plan")
            if (
                event.payload.get("owner") != actor_id
                or event.payload.get("visibility") != "private"
            ):
                raise ValueError("NPC plans must remain private to their owner")
            scheduled_for = _optional_datetime(event, "scheduled_for")
            due_at = _optional_datetime(event, "due_at")
            if scheduled_for is not None and due_at is not None and due_at < scheduled_for:
                raise ValueError("NPC plan deadline cannot precede its scheduled activity")
            people[actor_id] = replace(
                person,
                plan_id=_required(event, "plan_id"),
                plan_title=_required(event, "title"),
                plan_motivation=str(
                    event.payload.get("motivation", "response to privately owned evidence")
                ),
                plan_need=_optional(event, "motivation_need"),
                plan_goal_id=_optional(event, "goal_id"),
                plan_action=_required(event, "action"),
                plan_location_id=_required(event, "location_id"),
                plan_scheduled_for=scheduled_for,
                plan_due_at=due_at,
                plan_status="active",
            )
        elif event.kind == "npc.plan_interrupted":
            if person.plan_status != "active" or person.plan_id != _required(event, "plan_id"):
                raise ValueError("Only the active NPC plan can be interrupted")
            people[actor_id] = replace(person, plan_status="interrupted")
        elif event.kind == "npc.plan_completed":
            if person.plan_status != "active" or person.plan_id != _required(event, "plan_id"):
                raise ValueError("Only the active NPC plan can complete")
            people[actor_id] = replace(person, plan_status="completed")
        elif event.kind == "npc.plan_expired":
            if person.plan_status != "active" or person.plan_id != _required(event, "plan_id"):
                raise ValueError("Only the active NPC plan can expire")
            people[actor_id] = replace(person, plan_status="expired")
        elif event.kind in {"npc.goal_achieved", "npc.goal_abandoned"}:
            if person.goal_status != "active" or person.goal_id != _required(event, "goal_id"):
                raise ValueError("Only the active NPC goal can be resolved")
            people[actor_id] = replace(
                person,
                goal_status="achieved" if event.kind == "npc.goal_achieved" else "abandoned",
            )
        return NPCWorldState(people)


def project_npcs(events: Sequence[DomainEvent], now: datetime) -> NPCWorldState:
    if now.utcoffset() is None:
        raise ValueError("NPC projection time must be timezone-aware")
    explicit = any(event.kind == "npc.simulation_started" for event in events)
    state = NPCWorldState(
        {
            str(person["id"]): NPCState(
                actor_id=str(person["id"]),
                location_id="home" if explicit else npc_location(str(person["id"]), now.hour),
            )
            for person in PEOPLE
        }
    )
    for event in events:
        state = state.apply(event)
    return state


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _optional(event: DomainEvent, key: str) -> str | None:
    value = event.payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _bounded(event: DomainEvent, key: str) -> float:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"{key} must be between zero and one")
    return float(value)


def _optional_datetime(event: DomainEvent, key: str) -> datetime | None:
    value = event.payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{key} must be an ISO timestamp") from None
    if parsed.utcoffset() is None:
        raise ValueError(f"{key} must be timezone-aware")
    return parsed
