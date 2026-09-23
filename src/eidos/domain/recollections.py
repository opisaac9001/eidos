"""Replayable subjective recollections kept separate from source memories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Mapping, NamedTuple, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import GrowOnlyMap, IncrementalFold, PersistentMap


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
    remembered_person_id: str | None
    remembered_location_id: str | None
    remembered_at: datetime | None
    correction_evidence_id: str | None
    changed_at: datetime


@dataclass(frozen=True, slots=True)
class RecollectionState:
    latest: Mapping[str, Recollection]

    def __post_init__(self) -> None:
        object.__setattr__(self, "latest", MappingProxyType(dict(self.latest)))


class _RecollectionFold(NamedTuple):
    state: RecollectionState
    sources: PersistentMap[str, DomainEvent]
    accesses: PersistentMap[str, tuple[str, str | None]]
    access_counts: PersistentMap[str, int]
    used_accesses: GrowOnlyMap[str, bool]
    resisted_corrections: frozenset[tuple[str, str]]
    evidence: PersistentMap[str, DomainEvent]


def _count(counts: PersistentMap[str, int], memory_id: str) -> int:
    count = counts.get(memory_id)
    return 0 if count is None else count


def _replaced(
    latest: Mapping[str, Recollection], memory_id: str, recollection: Recollection
) -> Mapping[str, Recollection]:
    # Revisions are rare; copying the small map keeps every earlier fold state immutable.
    updated = dict(latest)
    updated[memory_id] = recollection
    return updated


def _recollection_step(fold: _RecollectionFold, event: DomainEvent) -> _RecollectionFold:
    sources = fold.sources
    accesses = fold.accesses
    access_counts = fold.access_counts
    used_accesses = fold.used_accesses
    resisted_corrections = fold.resisted_corrections
    evidence = fold.evidence
    latest = fold.state.latest
    if event.kind == "memory.recorded" and event.payload.get("owner", "pathos") == "pathos":
        sources = sources.with_item(str(event.event_id), event)
    elif event.kind == "memory.accessed":
        memory_id = event.payload.get("memory_id")
        if isinstance(memory_id, str):
            raw_time = event.payload.get("simulated_at")
            accesses = accesses.with_item(
                str(event.event_id),
                (memory_id, raw_time if isinstance(raw_time, str) else None),
            )
            access_counts = access_counts.with_item(memory_id, _count(access_counts, memory_id) + 1)
    elif event.kind == "memory.reminded":
        memory_id = _required(event, "memory_id")
        if memory_id not in sources:
            raise ValueError("Reminder requires an existing Pathos memory")
        cause = str(event.causation_id) if event.causation_id is not None else ""
        message = evidence.get(cause)
        if (
            message is None
            or message.kind != "conversation.message"
            or message.payload.get("speaker") != "you"
            or event.payload.get("source_message_id") != cause
            or event.payload.get("reminded_by") != "user"
        ):
            raise ValueError("Reminder requires its causal user message")
        expected = latest.get(memory_id)
        expected_confidence = (
            expected.confidence if expected is not None else _source_confidence(sources[memory_id])
        )
        expected_basis = expected.confidence_basis if expected is not None else "source_encoding"
        if (
            _level(event, "felt_confidence") != round(expected_confidence, 4)
            or event.payload.get("confidence_basis") != expected_basis
        ):
            raise ValueError("Reminder must preserve Pathos's current subjective certainty")
        if "remembered_at" in event.payload:
            expected_time = (
                expected.remembered_at
                if expected is not None and expected.remembered_at is not None
                else _source_time(sources[memory_id])
            )
            if _aware(event, "remembered_at") != expected_time:
                raise ValueError("Reminder must preserve Pathos's subjective memory time")
        _aware(event, "simulated_at")
        access_counts = access_counts.with_item(memory_id, _count(access_counts, memory_id) + 1)
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
        remembered_person_id = _remembered_attribution(
            event,
            "person_id",
            sources[memory_id],
            sources.get(blended_memory_ids[0]) if blended_memory_ids else None,
        )
        remembered_location_id = _remembered_attribution(
            event,
            "location_id",
            sources[memory_id],
            sources.get(blended_memory_ids[0]) if blended_memory_ids else None,
        )
        remembered_at = _remembered_time(
            event,
            sources[memory_id],
            sources.get(blended_memory_ids[0]) if blended_memory_ids else None,
            changed_at,
        )
        confidently_misattributed = confidence_basis == "familiarity_misattribution"
        if confidently_misattributed:
            if (
                not blended_memory_ids
                or event.payload.get("drift_kind") != "similarity_blend"
                or _count(access_counts, memory_id) < 4
            ):
                raise ValueError("Familiarity misattribution requires a rehearsed similarity blend")
            if confidence > 0.92:
                raise ValueError("Misattributed confidence cannot exceed its bounded ceiling")
            if detail_level not in {"clear", "partial"}:
                raise ValueError("A vivid misattribution must feel clear or partial")
        else:
            baseline = (
                prior.confidence if prior is not None else _source_confidence(sources[memory_id])
            )
            if confidence > baseline:
                raise ValueError("Ordinary reconsolidation cannot increase confidence")
            if detail_level not in {"partial", "vague"}:
                raise ValueError("Only imperfect recall can reconsolidate")
            if prior is not None and prior.detail_level == "vague" and detail_level == "partial":
                raise ValueError("Ordinary reconsolidation cannot restore lost detail")
        if prior is not None and changed_at < prior.changed_at:
            raise ValueError("Reconsolidation time cannot move backwards")
        latest = _replaced(
            latest,
            memory_id,
            Recollection(
                memory_id,
                revision,
                _required(event, "recalled_text"),
                confidence,
                confidence_basis,
                detail_level,
                affective_bias,
                blended_memory_ids,
                remembered_person_id,
                remembered_location_id,
                remembered_at,
                None,
                changed_at,
            ),
        )
        used_accesses = used_accesses.with_item(cause, True)
        if isinstance(blend_access, str):
            used_accesses = used_accesses.with_item(blend_access, True)
    elif event.kind == "memory.correction_resisted":
        memory_id = _required(event, "memory_id")
        source = sources.get(memory_id)
        prior = latest.get(memory_id)
        if source is None or prior is None:
            raise ValueError("Correction resistance requires a drifted Pathos memory")
        cause = str(event.causation_id) if event.causation_id is not None else ""
        direct = evidence.get(cause)
        if direct is None or direct.kind != "resource.confirmed":
            raise ValueError("Correction resistance requires direct contradictory evidence")
        if event.payload.get("evidence_event_id") != cause:
            raise ValueError("Correction resistance must preserve its evidence link")
        if not _evidence_contradicts(source, direct, event.payload.get("contradicting_value")):
            raise ValueError("Resisted evidence must contradict the source claim")
        if (
            prior.confidence_basis != "familiarity_misattribution"
            or prior.confidence < 0.85
            or _level(event, "felt_confidence") != prior.confidence
            or event.payload.get("confidence_basis") != prior.confidence_basis
        ):
            raise ValueError("Only a highly certain misattribution can resist correction")
        resisted_at = _aware(event, "simulated_at")
        if resisted_at < prior.changed_at:
            raise ValueError("Correction resistance time cannot move backwards")
        pair = (memory_id, cause)
        if pair in resisted_corrections:
            raise ValueError("Direct evidence can be resisted only once")
        resisted_corrections = resisted_corrections | {pair}
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
        if prior.confidence_basis == "familiarity_misattribution" and prior.confidence >= 0.85:
            independently_resisted = any(
                resisted_memory_id == memory_id and resisted_evidence_id != cause
                for resisted_memory_id, resisted_evidence_id in resisted_corrections
            )
            if not independently_resisted:
                raise ValueError(
                    "A highly certain misattribution requires independent corroboration"
                )
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
        latest = _replaced(
            latest,
            memory_id,
            Recollection(
                memory_id,
                revision,
                _required(event, "corrected_text"),
                confidence,
                "direct_confirmation",
                detail_level,
                0.0,
                (),
                None,
                None,
                None,
                cause,
                changed_at,
            ),
        )
    return _RecollectionFold(
        fold.state if latest is fold.state.latest else RecollectionState(latest),
        sources,
        accesses,
        access_counts,
        used_accesses,
        resisted_corrections,
        evidence.with_item(str(event.event_id), event),
    )


_RECOLLECTION_FOLD: IncrementalFold[_RecollectionFold] = IncrementalFold(
    lambda: _RecollectionFold(
        RecollectionState({}),
        PersistentMap(),
        PersistentMap(),
        PersistentMap(),
        GrowOnlyMap(),
        frozenset(),
        PersistentMap(),
    ),
    _recollection_step,
)


def project_recollections(events: Sequence[DomainEvent]) -> RecollectionState:
    return _RECOLLECTION_FOLD(events).state


def _evidence_contradicts(
    memory: DomainEvent, evidence: DomainEvent, claimed_value: object
) -> bool:
    subject = memory.payload.get("claim_subject_id")
    predicate = memory.payload.get("claim_predicate")
    old_value = memory.payload.get("claim_value")
    new_value = evidence.payload.get("object_value")
    return (
        isinstance(subject, str)
        and isinstance(predicate, str)
        and isinstance(old_value, str)
        and evidence.payload.get("subject_id") == subject
        and evidence.payload.get("predicate") == predicate
        and isinstance(new_value, str)
        and new_value != old_value
        and claimed_value == new_value
    )


def _remembered_attribution(
    event: DomainEvent,
    field: str,
    source: DomainEvent,
    blended_source: DomainEvent | None,
) -> str | None:
    payload_field = f"remembered_{field}"
    value = event.payload.get(payload_field)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"Recollection {payload_field} must be a non-empty string")
    if blended_source is None:
        raise ValueError("Changed attribution requires a source-linked memory blend")
    allowed = {
        candidate
        for candidate in (source.payload.get(field), blended_source.payload.get(field))
        if isinstance(candidate, str) and candidate
    }
    if value not in allowed:
        raise ValueError("Remembered attribution must come from a cited source memory")
    return value


def _remembered_time(
    event: DomainEvent,
    source: DomainEvent,
    blended_source: DomainEvent | None,
    changed_at: datetime,
) -> datetime | None:
    value = event.payload.get("remembered_at")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Recollection remembered_at must be an ISO timestamp")
    try:
        remembered_at = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("Recollection remembered_at must be an ISO timestamp") from None
    if remembered_at.utcoffset() is None:
        raise ValueError("Recollection remembered_at must be timezone-aware")
    if blended_source is None:
        raise ValueError("Changed memory time requires a source-linked memory blend")
    allowed = {_source_time(source), _source_time(blended_source)}
    if remembered_at not in allowed:
        raise ValueError("Remembered time must come from a cited source memory")
    if remembered_at > changed_at:
        raise ValueError("A recollection cannot borrow a future memory time")
    return remembered_at


def _source_time(event: DomainEvent) -> datetime:
    raw = event.payload.get("simulated_at")
    if isinstance(raw, datetime):
        value = raw
    elif isinstance(raw, str):
        try:
            value = datetime.fromisoformat(raw)
        except ValueError:
            value = event.occurred_at
    else:
        value = event.occurred_at
    if value.utcoffset() is None:
        raise ValueError("Memory source time must be timezone-aware")
    return value


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
