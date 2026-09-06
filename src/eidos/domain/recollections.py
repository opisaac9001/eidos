"""Replayable subjective recollections kept separate from source memories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class Recollection:
    memory_id: str
    revision: int
    text: str
    confidence: float
    detail_level: str
    changed_at: datetime


@dataclass(frozen=True, slots=True)
class RecollectionState:
    latest: Mapping[str, Recollection]

    def __post_init__(self) -> None:
        object.__setattr__(self, "latest", MappingProxyType(dict(self.latest)))


def project_recollections(events: Sequence[DomainEvent]) -> RecollectionState:
    sources: dict[str, float] = {}
    accesses: dict[str, str] = {}
    used_accesses: set[str] = set()
    latest: dict[str, Recollection] = {}
    for event in events:
        if event.kind == "memory.recorded" and event.payload.get("owner", "pathos") == "pathos":
            sources[str(event.event_id)] = _source_confidence(event)
        elif event.kind == "memory.accessed":
            memory_id = event.payload.get("memory_id")
            if isinstance(memory_id, str):
                accesses[str(event.event_id)] = memory_id
        elif event.kind == "memory.reconsolidated":
            memory_id = _required(event, "memory_id")
            if memory_id not in sources:
                raise ValueError("Reconsolidation requires an existing Pathos memory")
            cause = str(event.causation_id) if event.causation_id is not None else ""
            if accesses.get(cause) != memory_id:
                raise ValueError("Reconsolidation must be caused by recall of the same memory")
            if cause in used_accesses:
                raise ValueError("A memory access can cause only one reconsolidation")
            prior = latest.get(memory_id)
            revision = _integer(event, "revision")
            if revision != (prior.revision + 1 if prior else 1):
                raise ValueError("Recollection revision must be sequential")
            confidence = _level(event, "confidence")
            if prior is None and confidence > sources[memory_id]:
                raise ValueError("Reconsolidation cannot exceed source confidence")
            if prior is not None and confidence > prior.confidence:
                raise ValueError("Uncorrected reconsolidation cannot increase confidence")
            detail_level = _required(event, "detail_level")
            if detail_level not in {"partial", "vague"}:
                raise ValueError("Only imperfect recall can reconsolidate")
            if prior is not None and prior.detail_level == "vague" and detail_level == "partial":
                raise ValueError("Uncorrected reconsolidation cannot restore lost detail")
            if event.payload.get("epistemic_status") != "subjective_recollection":
                raise ValueError("Reconsolidation must remain explicitly subjective")
            changed_at = _aware(event, "simulated_at")
            if prior is not None and changed_at < prior.changed_at:
                raise ValueError("Reconsolidation time cannot move backwards")
            latest[memory_id] = Recollection(
                memory_id,
                revision,
                _required(event, "recalled_text"),
                confidence,
                detail_level,
                changed_at,
            )
            used_accesses.add(cause)
    return RecollectionState(latest)


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Recollection requires {key}")
    return value


def _integer(event: DomainEvent, key: str) -> int:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"Recollection {key} must be positive")
    return value


def _level(event: DomainEvent, key: str) -> float:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"Recollection {key} must be between zero and one")
    return float(value)


def _source_confidence(event: DomainEvent) -> float:
    value = event.payload.get("confidence", 1.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError("Memory confidence must be between zero and one")
    return float(value)


def _aware(event: DomainEvent, key: str) -> datetime:
    value = datetime.fromisoformat(_required(event, key))
    if value.utcoffset() is None:
        raise ValueError("Recollection time must be timezone-aware")
    return value
