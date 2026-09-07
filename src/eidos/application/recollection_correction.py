"""Correct subjective recollections only from newer direct structured evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.recollections import project_recollections


def recollection_correction_events(
    history: Sequence[DomainEvent], at: datetime
) -> list[DomainEvent]:
    if at.utcoffset() is None:
        raise ValueError("Recollection correction time must be timezone-aware")
    state = project_recollections(history)
    if not state.latest:
        return []
    sources = {
        str(event.event_id): event
        for event in history
        if event.kind == "memory.recorded" and event.payload.get("owner", "pathos") == "pathos"
    }
    corrected_pairs = {
        (str(event.payload.get("memory_id")), str(event.payload.get("evidence_event_id")))
        for event in history
        if event.kind == "memory.recollection_corrected"
    }
    last_corrected_values = {
        str(event.payload["memory_id"]): str(event.payload["corrected_value"])
        for event in history
        if event.kind == "memory.recollection_corrected"
        and isinstance(event.payload.get("memory_id"), str)
        and isinstance(event.payload.get("corrected_value"), str)
    }
    latest_change_positions = {
        str(event.payload["memory_id"]): position
        for position, event in enumerate(history)
        if event.kind in {"memory.reconsolidated", "memory.recollection_corrected"}
        and isinstance(event.payload.get("memory_id"), str)
    }
    output: list[DomainEvent] = []
    for position, evidence in enumerate(history):
        if evidence.kind != "resource.confirmed":
            continue
        evidence_id = str(evidence.event_id)
        evidence_time = _event_time(evidence)
        if evidence_time is None or evidence_time > at:
            continue
        for memory_id, recollection in state.latest.items():
            source = sources.get(memory_id)
            if (
                source is None
                or latest_change_positions.get(memory_id, len(history)) >= position
                or (memory_id, evidence_id) in corrected_pairs
                or not _contradicts(source, evidence)
                or last_corrected_values.get(memory_id) == evidence.payload.get("object_value")
            ):
                continue
            new_value = str(evidence.payload["object_value"])
            subject = str(evidence.payload["subject_id"])
            predicate = str(evidence.payload["predicate"]).replace("_", " ")
            evidence_confidence = _confidence(evidence)
            confidence = min(0.95, evidence_confidence)
            output.append(
                DomainEvent(
                    "memory.recollection_corrected",
                    "pathos",
                    {
                        "memory_id": memory_id,
                        "revision": recollection.revision + 1,
                        "corrected_text": (
                            f"I now remember that {subject} {predicate} was {new_value}; "
                            "my earlier recollection had that wrong."
                        ),
                        "corrected_value": new_value,
                        "confidence": round(confidence, 4),
                        "confidence_basis": "direct_confirmation",
                        "detail_level": "clear" if evidence_confidence >= 0.8 else "partial",
                        "evidence_event_id": evidence_id,
                        "correction_kind": "direct_confirmation",
                        "epistemic_status": "subjective_recollection",
                        "simulated_at": at.isoformat(),
                    },
                    causation_id=evidence.event_id,
                    correlation_id=f"recollection-{memory_id}",
                )
            )
            corrected_pairs.add((memory_id, evidence_id))
            return output
    return output


def _contradicts(memory: DomainEvent, evidence: DomainEvent) -> bool:
    subject = memory.payload.get("claim_subject_id")
    predicate = memory.payload.get("claim_predicate")
    old_value = memory.payload.get("claim_value")
    return (
        isinstance(subject, str)
        and isinstance(predicate, str)
        and isinstance(old_value, str)
        and evidence.payload.get("subject_id") == subject
        and evidence.payload.get("predicate") == predicate
        and isinstance(evidence.payload.get("object_value"), str)
        and evidence.payload.get("object_value") != old_value
    )


def _confidence(event: DomainEvent) -> float:
    value = event.payload.get("confidence", 1.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _event_time(event: DomainEvent) -> datetime | None:
    value = event.payload.get("simulated_at")
    if isinstance(value, datetime):
        return value if value.utcoffset() is not None else None
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.utcoffset() is not None else None
