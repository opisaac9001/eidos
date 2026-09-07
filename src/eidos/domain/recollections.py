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
    confidence_basis: str
    detail_level: str
    affective_bias: float
    blended_memory_ids: tuple[str, ...]
    correction_evidence_id: str | None
    changed_at: datetime


@dataclass(frozen=True, slots=True)
class RecollectionState:
    latest: Mapping[str, Recollection]

    def __post_init__(self) -> None:
        object.__setattr__(self, "latest", MappingProxyType(dict(self.latest)))


def project_recollections(events: Sequence[DomainEvent]) -> RecollectionState:
    sources: dict[str, DomainEvent] = {}
    accesses: dict[str, tuple[str, str | None]] = {}
    access_counts: dict[str, int] = {}
    used_accesses: set[str] = set()
    evidence: dict[str, DomainEvent] = {}
    latest: dict[str, Recollection] = {}
    for event in events:
        if event.kind == "memory.recorded" and event.payload.get("owner", "pathos") == "pathos":
            sources[str(event.event_id)] = event
        elif event.kind == "memory.accessed":
            memory_id = event.payload.get("memory_id")
            if isinstance(memory_id, str):
                raw_time = event.payload.get("simulated_at")
                accesses[str(event.event_id)] = (
                    memory_id,
                    raw_time if isinstance(raw_time, str) else None,
                )
                access_counts[memory_id] = access_counts.get(memory_id, 0) + 1
        elif event.kind == "memory.reconsolidated":
            memory_id = _required(event, "memory_id")
            if memory_id not in sources:
                raise ValueError("Reconsolidation requires an existing Pathos memory")
            changed_at = _aware(event, "simulated_at")
            cause = str(event.causation_id) if event.causation_id is not None else ""
            if not _access_matches(accesses.get(cause), memory_id, changed_at):
                raise ValueError("Reconsolidation must be caused by recall of the same memory")
            if cause in used_accesses:
                raise ValueError("A memory access can cause only one reconsolidation")
            prior = latest.get(memory_id)
            revision = _integer(event, "revision")
            if revision != (prior.revision + 1 if prior else 1):
                raise ValueError("Recollection revision must be sequential")
            confidence = _level(event, "confidence")
            confidence_basis = str(event.payload.get("confidence_basis", "degrading_recall"))
            if confidence_basis not in {"degrading_recall", "familiarity_misattribution"}:
                raise ValueError("Reconsolidation confidence basis is invalid")
            detail_level = _required(event, "detail_level")
            if event.payload.get("epistemic_status") != "subjective_recollection":
                raise ValueError("Reconsolidation must remain explicitly subjective")
            affective_bias = _signed_level(event.payload.get("affective_bias", 0.0))
            blended_memory_ids = _blended_sources(event)
            blend_access = event.payload.get("blend_access_id")
            if blended_memory_ids:
                if len(blended_memory_ids) != 1:
                    raise ValueError("A recollection can blend at most one related memory")
                blended_id = blended_memory_ids[0]
                if blended_id == memory_id or blended_id not in sources:
                    raise ValueError("A blend requires a different existing Pathos memory")
                if not isinstance(blend_access, str) or not _access_matches(
                    accesses.get(blend_access), blended_id, changed_at, require_time=True
                ):
                    raise ValueError("A blend must cite recall of its related memory")
                if blend_access in used_accesses or blend_access == cause:
                    raise ValueError("A memory access can contribute to only one reconsolidation")
            elif blend_access is not None:
                raise ValueError("A blend access requires a blended memory")
            confidently_misattributed = confidence_basis == "familiarity_misattribution"
            if confidently_misattributed:
                if (
                    not blended_memory_ids
                    or event.payload.get("drift_kind") != "similarity_blend"
                    or access_counts.get(memory_id, 0) < 4
                ):
                    raise ValueError(
                        "Familiarity misattribution requires a rehearsed similarity blend"
                    )
                if confidence > 0.92:
                    raise ValueError("Misattributed confidence cannot exceed its bounded ceiling")
                if detail_level not in {"clear", "partial"}:
                    raise ValueError("A vivid misattribution must feel clear or partial")
            else:
                baseline = (
                    prior.confidence
                    if prior is not None
                    else _source_confidence(sources[memory_id])
                )
                if confidence > baseline:
                    raise ValueError("Ordinary reconsolidation cannot increase confidence")
                if detail_level not in {"partial", "vague"}:
                    raise ValueError("Only imperfect recall can reconsolidate")
                if (
                    prior is not None
                    and prior.detail_level == "vague"
                    and detail_level == "partial"
                ):
                    raise ValueError("Ordinary reconsolidation cannot restore lost detail")
            if prior is not None and changed_at < prior.changed_at:
                raise ValueError("Reconsolidation time cannot move backwards")
            latest[memory_id] = Recollection(
                memory_id,
                revision,
                _required(event, "recalled_text"),
                confidence,
                confidence_basis,
                detail_level,
                affective_bias,
                blended_memory_ids,
                None,
                changed_at,
            )
            used_accesses.add(cause)
            if isinstance(blend_access, str):
                used_accesses.add(blend_access)
        elif event.kind == "memory.recollection_corrected":
            memory_id = _required(event, "memory_id")
            source = sources.get(memory_id)
            prior = latest.get(memory_id)
            if source is None or prior is None:
                raise ValueError("Correction requires an existing drifted Pathos memory")
            cause = str(event.causation_id) if event.causation_id is not None else ""
            direct = evidence.get(cause)
            if direct is None or direct.kind != "resource.confirmed":
                raise ValueError("Correction requires prior direct confirmation")
            if event.payload.get("evidence_event_id") != cause:
                raise ValueError("Correction must preserve its evidence link")
            subject = _required(source, "claim_subject_id")
            predicate = _required(source, "claim_predicate")
            old_value = _required(source, "claim_value")
            new_value = _required(direct, "object_value")
            if (
                direct.payload.get("subject_id") != subject
                or direct.payload.get("predicate") != predicate
                or new_value == old_value
                or event.payload.get("corrected_value") != new_value
            ):
                raise ValueError("Correction evidence must contradict the source claim")
            revision = _integer(event, "revision")
            if revision != prior.revision + 1:
                raise ValueError("Recollection correction revision must be sequential")
            confidence = _level(event, "confidence")
            evidence_confidence = _source_confidence(direct)
            if confidence > evidence_confidence:
                raise ValueError("Correction confidence cannot exceed direct evidence")
            detail_level = _required(event, "detail_level")
            if detail_level not in {"clear", "partial"}:
                raise ValueError("Correction detail must reflect direct evidence")
            if event.payload.get("epistemic_status") != "subjective_recollection":
                raise ValueError("Corrected recollection must remain subjective")
            changed_at = _aware(event, "simulated_at")
            if changed_at < prior.changed_at:
                raise ValueError("Recollection correction time cannot move backwards")
            latest[memory_id] = Recollection(
                memory_id,
                revision,
                _required(event, "corrected_text"),
                confidence,
                "direct_confirmation",
                detail_level,
                0.0,
                (),
                cause,
                changed_at,
            )
        evidence[str(event.event_id)] = event
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


def _signed_level(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not -1 <= value <= 1:
        raise ValueError("Recollection affective bias must be between negative and positive one")
    return float(value)


def _blended_sources(event: DomainEvent) -> tuple[str, ...]:
    value = event.payload.get("blended_memory_id")
    if value is None:
        return ()
    if not isinstance(value, str) or not value:
        raise ValueError("Blended memory id must be a non-empty string")
    return (value,)


def _access_matches(
    access: tuple[str, str | None] | None,
    memory_id: str,
    changed_at: datetime,
    *,
    require_time: bool = False,
) -> bool:
    if access is None or access[0] != memory_id:
        return False
    if access[1] is None:
        return not require_time
    try:
        accessed_at = datetime.fromisoformat(access[1])
    except ValueError:
        return False
    return accessed_at.utcoffset() is not None and accessed_at == changed_at


def _aware(event: DomainEvent, key: str) -> datetime:
    value = datetime.fromisoformat(_required(event, key))
    if value.utcoffset() is None:
        raise ValueError("Recollection time must be timezone-aware")
    return value
