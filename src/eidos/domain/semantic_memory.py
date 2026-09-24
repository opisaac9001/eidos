"""Replayable general expectations derived from Pathos's episodic memories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Mapping, NamedTuple, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, PersistentMap


@dataclass(frozen=True, slots=True)
class SemanticExpectation:
    expectation_id: str
    revision: int
    subject_id: str
    predicate: str
    object_value: str
    text: str
    confidence: float
    source_memory_ids: tuple[str, ...]
    distinct_days: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SemanticExpectationState:
    expectations: Mapping[str, SemanticExpectation]

    def __post_init__(self) -> None:
        object.__setattr__(self, "expectations", MappingProxyType(dict(self.expectations)))


def expectation_confidence(confidences: Sequence[float], distinct_days: int) -> float:
    if not confidences or distinct_days < 1:
        return 0.0
    average = sum(confidences) / len(confidences)
    return round(min(0.9, (0.48 + 0.05 * min(8, distinct_days)) * average), 4)


class _ExpectationFold(NamedTuple):
    sources: PersistentMap[str, DomainEvent]
    person_attribution: PersistentMap[str, str | None]
    location_attribution: PersistentMap[str, str | None]
    remembered_times: PersistentMap[str, datetime]
    felt_confidences: PersistentMap[str, float]
    latest: dict[str, SemanticExpectation]


def project_semantic_expectations(events: Sequence[DomainEvent]) -> SemanticExpectationState:
    return SemanticExpectationState(_EXPECTATION_FOLD(events).latest)


def _expectation_step(fold: _ExpectationFold, event: DomainEvent) -> _ExpectationFold:
    (
        sources,
        person_attribution,
        location_attribution,
        remembered_times,
        felt_confidences,
        latest,
    ) = fold
    if event.kind == "memory.recorded" and event.payload.get("owner", "pathos") == "pathos":
        memory_id = str(event.event_id)
        sources = sources.with_item(memory_id, event)
        person_attribution = person_attribution.with_item(
            memory_id, _optional_string(event, "person_id")
        )
        location_attribution = location_attribution.with_item(
            memory_id, _optional_string(event, "location_id")
        )
        remembered_times = remembered_times.with_item(memory_id, _event_time(event))
        felt_confidences = felt_confidences.with_item(memory_id, _confidence(event))
    elif event.kind == "memory.reconsolidated":
        raw_memory_id = event.payload.get("memory_id")
        source = sources.get(str(raw_memory_id))
        if source is None:
            return fold
        memory_id = str(raw_memory_id)
        person_attribution = person_attribution.with_item(
            memory_id,
            _optional_string(event, "remembered_person_id")
            or _optional_string(source, "person_id"),
        )
        location_attribution = location_attribution.with_item(
            memory_id,
            _optional_string(event, "remembered_location_id")
            or _optional_string(source, "location_id"),
        )
        remembered_times = remembered_times.with_item(
            memory_id, _optional_time(event, "remembered_at") or _event_time(source)
        )
        felt_confidences = felt_confidences.with_item(memory_id, _confidence(event))
    elif event.kind == "memory.recollection_corrected":
        raw_memory_id = event.payload.get("memory_id")
        source = sources.get(str(raw_memory_id))
        if source is None:
            return fold
        memory_id = str(raw_memory_id)
        person_attribution = person_attribution.with_item(
            memory_id, _optional_string(source, "person_id")
        )
        location_attribution = location_attribution.with_item(
            memory_id, _optional_string(source, "location_id")
        )
        remembered_times = remembered_times.with_item(memory_id, _event_time(source))
        felt_confidences = felt_confidences.with_item(memory_id, _confidence(event))
    elif event.kind in {
        "semantic.expectation_formed",
        "semantic.expectation_reinforced",
        "semantic.expectation_revised",
    }:
        expectation_id = _required(event, "expectation_id")
        revision = _positive_integer(event, "revision")
        prior = latest.get(expectation_id)
        if revision != (prior.revision + 1 if prior is not None else 1):
            raise ValueError("Semantic expectation revision must be sequential")
        if prior is None and event.kind != "semantic.expectation_formed":
            raise ValueError("A semantic expectation must be formed before revision")
        if prior is not None:
            same_value = prior.object_value == event.payload.get("object_value")
            expected_kind = (
                "semantic.expectation_reinforced" if same_value else "semantic.expectation_revised"
            )
            if event.kind != expected_kind:
                raise ValueError("Semantic expectation event kind does not match its change")
        if event.payload.get("epistemic_status") != "subjective_generalization":
            raise ValueError("Semantic expectations must remain explicitly subjective")
        subject_id = _required(event, "subject_id")
        predicate = _required(event, "predicate")
        object_value = _required(event, "object_value")
        text = _required(event, "text")
        if predicate != "usually_at":
            raise ValueError("Unsupported semantic expectation predicate")
        if expectation_id != f"pathos-person-usually-at:{subject_id}":
            raise ValueError("Semantic expectation ID must match its subject")
        if prior is not None and (prior.subject_id != subject_id or prior.predicate != predicate):
            raise ValueError("Semantic expectation subject and predicate are stable")
        source_ids = _source_ids(event)
        if not 3 <= len(source_ids) <= 8:
            raise ValueError("Semantic expectation needs three to eight source memories")
        if _positive_integer(event, "source_count") != len(source_ids):
            raise ValueError("Semantic expectation source count must match its sources")
        source_days: set[str] = set()
        confidences: list[float] = []
        for memory_id in source_ids:
            source = sources.get(memory_id)
            if source is None or source.payload.get("category") == "dream":
                raise ValueError("Semantic expectation source must be a lived Pathos memory")
            if (
                person_attribution.get(memory_id) != subject_id
                or location_attribution.get(memory_id) != object_value
            ):
                raise ValueError("Semantic expectation source does not support its pattern")
            source_days.add(remembered_times[memory_id].date().isoformat())
            confidences.append(felt_confidences[memory_id])
        distinct_days = _positive_integer(event, "distinct_days")
        if distinct_days != len(source_days) or distinct_days < 3:
            raise ValueError("Semantic expectation requires three distinct remembered days")
        confidence = _level(event, "confidence")
        if confidence != expectation_confidence(confidences, distinct_days):
            raise ValueError("Semantic expectation confidence must derive from its sources")
        updated_at = _aware(event, "simulated_at")
        if prior is not None and updated_at < prior.updated_at:
            raise ValueError("Semantic expectation time cannot move backwards")
        latest = {
            **latest,
            expectation_id: SemanticExpectation(
                expectation_id,
                revision,
                subject_id,
                predicate,
                object_value,
                text,
                confidence,
                source_ids,
                distinct_days,
                updated_at,
            ),
        }
    return _ExpectationFold(
        sources,
        person_attribution,
        location_attribution,
        remembered_times,
        felt_confidences,
        latest,
    )


_EXPECTATION_FOLD: IncrementalFold[_ExpectationFold] = IncrementalFold(
    lambda: _ExpectationFold(
        PersistentMap(), PersistentMap(), PersistentMap(), PersistentMap(), PersistentMap(), {}
    ),
    _expectation_step,
)


def _source_ids(event: DomainEvent) -> tuple[str, ...]:
    raw = _required(event, "source_memory_ids")
    values = tuple(item for item in raw.split(",") if item)
    if len(set(values)) != len(values):
        raise ValueError("Semantic expectation source memories must be unique")
    return values


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Semantic expectation requires {key}")
    return value


def _optional_string(event: DomainEvent, key: str) -> str | None:
    value = event.payload.get(key)
    return value if isinstance(value, str) and value else None


def _positive_integer(event: DomainEvent, key: str) -> int:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"Semantic expectation {key} must be positive")
    return value


def _level(event: DomainEvent, key: str) -> float:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"Semantic expectation {key} must be between zero and one")
    return float(value)


def _confidence(event: DomainEvent) -> float:
    value = event.payload.get("confidence", 1.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError("Memory confidence must be between zero and one")
    return float(value)


def _optional_time(event: DomainEvent, key: str) -> datetime | None:
    value = event.payload.get(key)
    if value is None:
        return None
    return _parse_time(value, f"Semantic expectation {key}")


def _event_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at", event.occurred_at)
    return _parse_time(value, "Memory time")


def _aware(event: DomainEvent, key: str) -> datetime:
    return _parse_time(event.payload.get(key), f"Semantic expectation {key}")


def _parse_time(value: object, label: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError(f"{label} must be an ISO timestamp") from None
    else:
        raise ValueError(f"{label} must be an ISO timestamp")
    if parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed
