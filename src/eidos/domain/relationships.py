"""Replayable directed relationship state derived from witnessed evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold


@dataclass(frozen=True, slots=True)
class Relationship:
    person_id: str
    encounters: int = 0
    trust: float = 0.3
    familiarity: float = 0.2
    tension: float = 0.0


@dataclass(frozen=True, slots=True)
class RelationshipState:
    relationships: Mapping[str, Relationship]

    def __post_init__(self) -> None:
        object.__setattr__(self, "relationships", MappingProxyType(dict(self.relationships)))

    @classmethod
    def empty(cls) -> RelationshipState:
        return cls({})

    def for_person(self, person_id: str) -> Relationship:
        return self.relationships.get(person_id, Relationship(person_id))

    def apply(self, event: DomainEvent) -> RelationshipState:
        person_id = event.payload.get("person_id")
        if event.kind not in {"npc.encountered", "relationship.changed"}:
            return self
        if not isinstance(person_id, str) or not person_id.strip():
            raise ValueError("Relationship evidence requires a person")
        relationships = dict(self.relationships)
        current = self.for_person(person_id)
        if event.kind == "npc.encountered":
            relationships[person_id] = replace(
                current,
                encounters=current.encounters + 1,
                familiarity=min(1.0, current.familiarity + 0.01),
            )
        else:
            changes: dict[str, float] = {}
            for dimension in ("trust", "familiarity", "tension"):
                value = event.payload.get(f"{dimension}_delta", 0.0)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("Relationship changes must be numeric")
                changes[dimension] = max(0.0, min(1.0, getattr(current, dimension) + float(value)))
            relationships[person_id] = replace(
                current,
                trust=changes["trust"],
                familiarity=changes["familiarity"],
                tension=changes["tension"],
            )
        return RelationshipState(relationships)

    def materialized_state(self) -> Mapping[str, Any]:
        return {"relationships": [asdict(item) for item in self.relationships.values()]}

    @classmethod
    def from_materialized_state(cls, raw: Mapping[str, Any]) -> RelationshipState:
        if set(raw) != {"relationships"} or not isinstance(raw["relationships"], list):
            raise ValueError("Materialized relationship fields do not match schema v1")
        restored: dict[str, Relationship] = {}
        expected = set(Relationship.__dataclass_fields__)
        for value in raw["relationships"]:
            if not isinstance(value, dict) or set(value) != expected:
                raise ValueError("Materialized relationship record does not match schema v1")
            try:
                item = Relationship(**value)
            except TypeError:
                raise ValueError("Materialized relationship record is invalid") from None
            dimensions = (item.trust, item.familiarity, item.tension)
            if (
                not isinstance(item.person_id, str)
                or not item.person_id.strip()
                or item.person_id in restored
                or isinstance(item.encounters, bool)
                or not isinstance(item.encounters, int)
                or item.encounters < 0
                or any(
                    isinstance(number, bool)
                    or not isinstance(number, (int, float))
                    or not 0 <= number <= 1
                    for number in dimensions
                )
            ):
                raise ValueError("Materialized relationship is semantically invalid")
            restored[item.person_id] = item
        return cls(restored)


_RELATIONSHIPS_FOLD: IncrementalFold[RelationshipState] = IncrementalFold(
    lambda: RelationshipState.empty(), lambda state, event: state.apply(event)
)


def project_relationships(events: Sequence[DomainEvent]) -> RelationshipState:
    return _RELATIONSHIPS_FOLD(events)
