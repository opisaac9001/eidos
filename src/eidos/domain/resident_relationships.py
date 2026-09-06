"""Directed relationships that residents hold toward one another."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType

from eidos.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class ResidentRelationship:
    owner_id: str
    person_id: str
    encounters: int = 0
    trust: float = 0.3
    familiarity: float = 0.15
    tension: float = 0.0
    last_scene_id: str | None = None


@dataclass(frozen=True, slots=True)
class ResidentRelationshipState:
    relationships: Mapping[tuple[str, str], ResidentRelationship]

    def __post_init__(self) -> None:
        object.__setattr__(self, "relationships", MappingProxyType(dict(self.relationships)))

    @classmethod
    def empty(cls) -> ResidentRelationshipState:
        return cls({})

    def between(self, owner_id: str, person_id: str) -> ResidentRelationship:
        return self.relationships.get(
            (owner_id, person_id), ResidentRelationship(owner_id, person_id)
        )

    def apply(self, event: DomainEvent) -> ResidentRelationshipState:
        if event.kind != "npc.relationship_changed":
            return self
        owner_id = _required(event, "owner")
        person_id = _required(event, "person_id")
        if owner_id == person_id:
            raise ValueError("A resident relationship needs two different people")
        if event.payload.get("visibility") != "private":
            raise ValueError("A resident's relationship state must remain private")
        current = self.between(owner_id, person_id)
        relationships = dict(self.relationships)
        relationships[(owner_id, person_id)] = replace(
            current,
            encounters=current.encounters + 1,
            trust=_changed(current.trust, event, "trust"),
            familiarity=_changed(current.familiarity, event, "familiarity"),
            tension=_changed(current.tension, event, "tension"),
            last_scene_id=_required(event, "scene_id"),
        )
        return ResidentRelationshipState(relationships)


def project_resident_relationships(
    events: Sequence[DomainEvent],
) -> ResidentRelationshipState:
    state = ResidentRelationshipState.empty()
    prior: dict[str, DomainEvent] = {}
    for event in events:
        if event.kind == "npc.relationship_changed":
            source_id = _required(event, "source_turn_event_id")
            turn = prior.get(source_id)
            owner_id = _required(event, "owner")
            person_id = _required(event, "person_id")
            if turn is None or turn.kind != "scene.turn_taken":
                raise ValueError("Resident relationship change needs a prior spoken turn")
            if (
                event.causation_id != turn.event_id
                or turn.payload.get("scene_id") != event.payload.get("scene_id")
                or {owner_id, person_id}
                != {turn.payload.get("actor_id"), turn.payload.get("audience_id")}
            ):
                raise ValueError("Resident relationship evidence does not match its scene")
        state = state.apply(event)
        prior[str(event.event_id)] = event
    return state


def _changed(current: float, event: DomainEvent, dimension: str) -> float:
    value = event.payload.get(f"{dimension}_delta", 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Resident relationship changes must be numeric")
    return max(0.0, min(1.0, current + float(value)))


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value.strip()
