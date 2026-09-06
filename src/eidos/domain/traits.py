"""Slow behavioral tendencies derived from authoritative outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent

DEFAULT_TRAITS: Mapping[str, float] = {
    "openness": 0.68,
    "sociability": 0.52,
    "follow_through": 0.64,
}
MAX_DRIFT = 0.15


@dataclass(frozen=True, slots=True)
class TraitState:
    levels: Mapping[str, float]

    def __post_init__(self) -> None:
        object.__setattr__(self, "levels", MappingProxyType(dict(self.levels)))


def trait_evidence(event: DomainEvent) -> tuple[tuple[str, int], ...]:
    """Classify only realized choices and resolved consequences as trait evidence."""
    if event.kind == "agency.activity_realized":
        action = event.payload.get("action")
        evidence: list[tuple[str, int]] = []
        if action in {"attend", "learn"}:
            evidence.append(("openness", 1))
        if isinstance(event.payload.get("companion_id"), str):
            evidence.append(("sociability", 1))
        if action == "work":
            evidence.append(("follow_through", 1))
        return tuple(evidence)
    if event.kind in {"self_project.completed", "commitment.fulfilled"}:
        return (("follow_through", 1),)
    if event.kind in {"self_project.failed", "commitment.missed"}:
        return (("follow_through", -1),)
    return ()


def project_traits(history: Sequence[DomainEvent]) -> TraitState:
    levels = dict(DEFAULT_TRAITS)
    last_change: datetime | None = None
    last_change_by_trait: dict[str, datetime] = {}
    seen: dict[str, DomainEvent] = {}
    for event in history:
        if event.kind != "trait.adjusted":
            seen[str(event.event_id)] = event
            continue
        if not any(item.kind == "identity.established" for item in seen.values()):
            raise ValueError("Traits cannot develop before identity exists")
        trait_id = _required(event, "trait_id")
        if trait_id not in DEFAULT_TRAITS:
            raise ValueError("Unknown trait")
        direction = event.payload.get("direction")
        delta = _number(event, "delta")
        prior = _number(event, "prior")
        next_level = _number(event, "next")
        if direction not in {-1, 1}:
            raise ValueError("Trait direction must be -1 or 1")
        change = delta
        if not 0 < change <= 0.02 or abs(prior - levels[trait_id]) > 1e-9:
            raise ValueError("Trait adjustment has an invalid prior or delta")
        expected = max(
            DEFAULT_TRAITS[trait_id] - MAX_DRIFT,
            min(DEFAULT_TRAITS[trait_id] + MAX_DRIFT, levels[trait_id] + direction * change),
        )
        if abs(next_level - expected) > 1e-9:
            raise ValueError("Trait adjustment does not match its evidence")
        source_ids = [_required(event, f"source_event_{position}") for position in range(1, 6)]
        if len(set(source_ids)) != 5:
            raise ValueError("Trait adjustment requires five distinct sources")
        sources = [seen.get(source_id) for source_id in source_ids]
        if any(source is None for source in sources):
            raise ValueError("Trait adjustment cites unknown evidence")
        typed_sources = [source for source in sources if source is not None]
        if any((trait_id, direction) not in trait_evidence(source) for source in typed_sources):
            raise ValueError("Trait evidence does not support the adjustment")
        source_times = [_event_time(source) for source in typed_sources]
        changed_at = _event_time(event)
        if max(source_times) - min(source_times) < timedelta(days=30):
            raise ValueError("Trait evidence must span at least thirty days")
        if max(source_times) > changed_at:
            raise ValueError("Trait evidence cannot come from the future")
        previous_trait_change = last_change_by_trait.get(trait_id)
        if previous_trait_change is not None and min(source_times) <= previous_trait_change:
            raise ValueError("Trait evidence cannot be reused")
        if last_change is not None and changed_at - last_change < timedelta(days=30):
            raise ValueError("Trait changes must be at least thirty days apart")
        levels[trait_id] = expected
        last_change = changed_at
        last_change_by_trait[trait_id] = changed_at
        seen[str(event.event_id)] = event
    return TraitState(levels)


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _number(event: DomainEvent, key: str) -> float:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Trait levels and delta must be numeric")
    return float(value)


def _event_time(event: DomainEvent) -> datetime:
    parsed = datetime.fromisoformat(_required(event, "simulated_at"))
    if parsed.utcoffset() is None:
        raise ValueError("Trait development time must be timezone-aware")
    return parsed
