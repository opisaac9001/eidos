"""Replayable autobiographical interpretations grounded in Pathos's own outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Mapping, NamedTuple, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, PersistentMap
from eidos.domain.traits import trait_evidence


@dataclass(frozen=True, slots=True)
class SelfConcept:
    concept_id: str
    revision: int
    dimension: str
    stance: str
    text: str
    confidence: float
    positive_count: int
    negative_count: int
    source_event_ids: tuple[str, ...]
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class SelfConceptState:
    concepts: Mapping[str, SelfConcept]

    def __post_init__(self) -> None:
        object.__setattr__(self, "concepts", MappingProxyType(dict(self.concepts)))


def follow_through_direction(event: DomainEvent) -> int | None:
    if event.aggregate_id != "pathos":
        return None
    for trait_id, direction in trait_evidence(event):
        if trait_id == "follow_through":
            return direction
    return None


def self_concept_stance(directions: Sequence[int]) -> str:
    if not directions:
        raise ValueError("Self-concept stance requires evidence")
    score = sum(directions) / len(directions)
    if score >= 0.34:
        return "dependable"
    if score <= -0.34:
        return "struggling"
    return "uneven"


def self_concept_text(stance: str) -> str:
    if stance == "dependable":
        return "Lately, I see myself as someone who usually follows through on what I take on."
    if stance == "struggling":
        return "Lately, I see myself as someone who has been struggling to follow through."
    if stance == "uneven":
        return "Lately, my follow-through has felt uneven to me."
    raise ValueError("Unknown self-concept stance")


def self_concept_confidence(directions: Sequence[int], span_days: int) -> float:
    if not directions or span_days < 0:
        return 0.0
    consistency = abs(sum(directions) / len(directions))
    evidence_strength = min(0.88, 0.44 + 0.04 * len(directions) + 0.02 * min(6, span_days // 7))
    return round(evidence_strength * (0.72 + 0.28 * consistency), 4)


class _SelfConceptFold(NamedTuple):
    latest: dict[str, SelfConcept]
    # Every earlier event by id, the latest one winning, as evidence a concept may cite.
    evidence: PersistentMap[str, DomainEvent]


def project_self_concepts(events: Sequence[DomainEvent]) -> SelfConceptState:
    return SelfConceptState(_SELF_CONCEPT_FOLD(events).latest)


def _self_concept_step(fold: _SelfConceptFold, event: DomainEvent) -> _SelfConceptFold:
    latest = fold.latest
    if event.kind in {
        "self_concept.formed",
        "self_concept.reinforced",
        "self_concept.revised",
    }:
        latest = dict(latest)
        _apply_self_concept(latest, fold.evidence, event)
    return _SelfConceptFold(latest, fold.evidence.with_item(str(event.event_id), event))


def _apply_self_concept(
    latest: dict[str, SelfConcept], evidence: PersistentMap[str, DomainEvent], event: DomainEvent
) -> None:
    if event.aggregate_id != "pathos" or event.payload.get("epistemic_status") != (
        "subjective_self_interpretation"
    ):
        raise ValueError("Self-concepts must remain Pathos's subjective interpretation")
    concept_id = _required(event, "concept_id")
    dimension = _required(event, "dimension")
    if concept_id != "pathos-self-concept:follow_through" or dimension != "follow_through":
        raise ValueError("Unsupported self-concept identity")
    revision = _positive_integer(event, "revision")
    prior = latest.get(concept_id)
    if revision != (prior.revision + 1 if prior is not None else 1):
        raise ValueError("Self-concept revision must be sequential")
    if prior is None and event.kind != "self_concept.formed":
        raise ValueError("A self-concept must be formed before revision")
    source_ids = tuple(
        _required(event, f"source_event_{position}")
        for position in range(1, _positive_integer(event, "source_count") + 1)
    )
    if not 3 <= len(source_ids) <= 8 or len(set(source_ids)) != len(source_ids):
        raise ValueError("A self-concept needs three to eight distinct sources")
    sources = [evidence.get(source_id) for source_id in source_ids]
    if any(source is None for source in sources):
        raise ValueError("Self-concept cites unknown evidence")
    known_sources = [source for source in sources if source is not None]
    directions = [follow_through_direction(source) for source in known_sources]
    if any(direction is None for direction in directions):
        raise ValueError("Self-concept evidence does not support its dimension")
    typed_directions = [direction for direction in directions if direction is not None]
    source_times = [_event_time(source) for source in known_sources]
    distinct_days = {source_time.date() for source_time in source_times}
    if len(distinct_days) < 3 or max(source_times) - min(source_times) < timedelta(days=7):
        raise ValueError("Self-concept evidence must span three days and one week")
    updated_at = _event_time(event)
    if max(source_times) > updated_at:
        raise ValueError("Self-concept evidence cannot come from the future")
    if prior is not None:
        if updated_at - prior.updated_at < timedelta(days=14):
            raise ValueError("Self-concept revisions must be at least fourteen days apart")
        if not set(source_ids) - set(prior.source_event_ids):
            raise ValueError("Self-concept revision requires new evidence")
    stance = self_concept_stance(typed_directions)
    expected_kind = (
        "self_concept.formed"
        if prior is None
        else "self_concept.reinforced"
        if prior.stance == stance
        else "self_concept.revised"
    )
    if event.kind != expected_kind:
        raise ValueError("Self-concept event kind does not match its change")
    if _required(event, "stance") != stance or _required(event, "text") != self_concept_text(
        stance
    ):
        raise ValueError("Self-concept interpretation must derive from its evidence")
    positive_count = sum(direction > 0 for direction in typed_directions)
    negative_count = len(typed_directions) - positive_count
    if (
        _nonnegative_integer(event, "positive_count") != positive_count
        or _nonnegative_integer(event, "negative_count") != negative_count
    ):
        raise ValueError("Self-concept outcome counts must match its evidence")
    span_days = (max(source_times).date() - min(source_times).date()).days
    confidence = _level(event, "confidence")
    if confidence != self_concept_confidence(typed_directions, span_days):
        raise ValueError("Self-concept confidence must derive from its evidence")
    latest[concept_id] = SelfConcept(
        concept_id,
        revision,
        dimension,
        stance,
        self_concept_text(stance),
        confidence,
        positive_count,
        negative_count,
        source_ids,
        updated_at,
    )


_SELF_CONCEPT_FOLD: IncrementalFold[_SelfConceptFold] = IncrementalFold(
    lambda: _SelfConceptFold({}, PersistentMap()), _self_concept_step
)


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Self-concept requires {key}")
    return value


def _positive_integer(event: DomainEvent, key: str) -> int:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"Self-concept {key} must be positive")
    return value


def _nonnegative_integer(event: DomainEvent, key: str) -> int:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Self-concept {key} must be nonnegative")
    return value


def _level(event: DomainEvent, key: str) -> float:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"Self-concept {key} must be between zero and one")
    return float(value)


def _event_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError("Self-concept time must be an ISO timestamp") from None
    else:
        raise ValueError("Self-concept evidence needs simulated time")
    if parsed.utcoffset() is None:
        raise ValueError("Self-concept time must be timezone-aware")
    return parsed
