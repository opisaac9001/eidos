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
    energy: float = 0.7
    connection: float = 0.5
    purpose: float = 0.5
    private_activity: str = "unrecorded"


@dataclass(frozen=True, slots=True)
class NPCWorldState:
    people: Mapping[str, NPCState]

    def __post_init__(self) -> None:
        object.__setattr__(self, "people", MappingProxyType(dict(self.people)))

    def apply(self, event: DomainEvent) -> NPCWorldState:
        people = dict(self.people)
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


def _bounded(event: DomainEvent, key: str) -> float:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"{key} must be between zero and one")
    return float(value)
