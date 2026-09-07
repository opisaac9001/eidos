"""Persist bounded drift after Pathos actually uses an imperfect recollection."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Sequence

from eidos.application.memory import RecalledMemory, terms
from eidos.domain.events import DomainEvent
from eidos.domain.recollections import project_recollections

_COOLDOWN = timedelta(days=30)


def reconsolidation_events(
    history: Sequence[DomainEvent], recalled: Sequence[RecalledMemory], at: datetime
) -> list[DomainEvent]:
    if at.utcoffset() is None:
        raise ValueError("Reconsolidation time must be timezone-aware")
    state = project_recollections(history)
    affective_bias = _current_affect(history, at)
    output: list[DomainEvent] = []
    already_used: set[str] = set()
    for event in history:
        if event.kind != "memory.reconsolidated":
            continue
        if event.causation_id is not None:
            already_used.add(str(event.causation_id))
        blend_access_id = event.payload.get("blend_access_id")
        if isinstance(blend_access_id, str):
            already_used.add(blend_access_id)
    for item in recalled:
        if item.detail_level not in {"partial", "vague"}:
            continue
        memory_id = str(item.event.event_id)
        prior = state.latest.get(memory_id)
        if prior is not None and at - prior.changed_at < _COOLDOWN:
            continue
        access = _unused_access(history, memory_id, already_used, at)
        if access is None:
            continue
        companion = _blend_candidate(item, recalled)
        blend_access = (
            _unused_access(history, str(companion.event.event_id), already_used, at)
            if companion is not None
            else None
        )
        if companion is not None and blend_access is None:
            companion = None
        revision = prior.revision + 1 if prior else 1
        source_confidence = float(item.event.payload.get("confidence", 1.0))
        access_count = _access_count(history, memory_id)
        confidently_misattributed = companion is not None and access_count >= 4
        if confidently_misattributed:
            # Repetition can be mistaken for evidence. The memory feels clearer
            # because it is familiar, even though its details now mix two sources.
            confidence = min(0.92, 0.82 + 0.025 * min(4, access_count))
            confidence_basis = "familiarity_misattribution"
            detail_level = "clear"
        else:
            confidence = min(
                prior.confidence if prior else source_confidence,
                max(0.15, item.accessibility * (0.94**revision)),
            )
            confidence_basis = "degrading_recall"
            detail_level = item.detail_level
        payload: dict[str, object] = {
            "memory_id": memory_id,
            "revision": revision,
            "recalled_text": _drift_text(
                item.recalled_text,
                item.detail_level,
                revision,
                affective_bias,
                companion.recalled_text if companion is not None else None,
                confidently_misattributed,
            ),
            "confidence": round(confidence, 4),
            "confidence_basis": confidence_basis,
            "detail_level": detail_level,
            "affective_bias": round(affective_bias, 4),
            "drift_kind": (
                "similarity_blend"
                if companion is not None
                else "gist_only"
                if item.detail_level == "vague"
                else "detail_loss"
            ),
            "epistemic_status": "subjective_recollection",
            "simulated_at": at.isoformat(),
        }
        if blend_access is not None:
            payload["blend_access_id"] = str(blend_access.event_id)
        if companion is not None:
            payload["blended_memory_id"] = str(companion.event.event_id)
            for field in ("person_id", "location_id"):
                source_value = item.event.payload.get(field)
                companion_value = companion.event.payload.get(field)
                if (
                    isinstance(companion_value, str)
                    and companion_value
                    and companion_value != source_value
                ):
                    payload[f"remembered_{field}"] = companion_value
            source_time = _event_time(item.event)
            companion_time = _event_time(companion.event)
            if companion_time != source_time:
                payload["remembered_at"] = companion_time.isoformat()
        output.append(
            DomainEvent(
                "memory.reconsolidated",
                "pathos",
                payload,
                causation_id=access.event_id,
                correlation_id=f"recollection-{memory_id}",
            )
        )
        # A conversation can surface several related traces, but only the most
        # salient imperfect recollection should be rewritten by that act of recall.
        # This keeps reconsolidation selective instead of mechanically corrupting
        # every memory that happened to be supplied as context.
        break
    return output


def _drift_text(
    text: str,
    detail_level: str,
    revision: int,
    affective_bias: float,
    blended_text: str | None,
    confidently_misattributed: bool,
) -> str:
    clause = re.split(r"[,;.!?]", text, maxsplit=1)[0].strip()
    clause = re.sub(r"^I remember\s+", "", clause, flags=re.IGNORECASE).strip()
    if detail_level == "vague":
        drifted = f"Something about {clause.lower()} still feels familiar, but I cannot place it."
    elif revision % 2:
        drifted = f"I mostly remember {clause.lower()}, though I may be missing the context."
    else:
        drifted = f"I think {clause.lower()}, but the surrounding details no longer feel reliable."
    if blended_text is not None:
        blended_clause = re.split(r"[,;.!?]", blended_text, maxsplit=1)[0].strip().lower()
        blended_clause = re.sub(r"^i (?:mostly )?(?:remember|think)\s+", "", blended_clause)
        if confidently_misattributed:
            drifted = f"I remember {clause.lower()}, and {blended_clause} was part of it."
        else:
            drifted = f"{drifted} I also picture {blended_clause} as part of it."
    if affective_bias <= -0.25:
        return f"{drifted} It feels heavier to me now."
    if affective_bias >= 0.25:
        return f"{drifted} It feels warmer to me now."
    return drifted


def _access_count(history: Sequence[DomainEvent], memory_id: str) -> int:
    return sum(
        event.kind in {"memory.accessed", "memory.reminded"}
        and event.payload.get("memory_id") == memory_id
        for event in history
    )


def _unused_access(
    history: Sequence[DomainEvent], memory_id: str, used: set[str], at: datetime
) -> DomainEvent | None:
    for event in reversed(history):
        if (
            event.kind != "memory.accessed"
            or event.payload.get("memory_id") != memory_id
            or str(event.event_id) in used
        ):
            continue
        raw_time = event.payload.get("simulated_at")
        if isinstance(raw_time, str):
            accessed_at = datetime.fromisoformat(raw_time)
            if accessed_at.utcoffset() is not None and accessed_at == at:
                return event
    return None


def _blend_candidate(
    primary: RecalledMemory, recalled: Sequence[RecalledMemory]
) -> RecalledMemory | None:
    primary_terms = terms(primary.recalled_text)
    best: tuple[float, RecalledMemory] | None = None
    for candidate in recalled:
        if candidate.event.event_id == primary.event.event_id or candidate.detail_level not in {
            "partial",
            "vague",
        }:
            continue
        candidate_terms = terms(candidate.recalled_text)
        overlap = len(primary_terms & candidate_terms) / max(
            1, min(len(primary_terms), len(candidate_terms))
        )
        metadata_bonus = 0.0
        for key, weight in (("person_id", 0.2), ("object_id", 0.2), ("location_id", 0.1)):
            value = primary.event.payload.get(key)
            if isinstance(value, str) and value == candidate.event.payload.get(key):
                metadata_bonus += weight
        similarity = overlap + metadata_bonus
        if similarity < 0.35:
            continue
        if best is None or similarity > best[0]:
            best = (similarity, candidate)
    return best[1] if best is not None else None


def _current_affect(history: Sequence[DomainEvent], at: datetime) -> float:
    for event in reversed(history):
        if event.kind not in {"emotion.sampled", "affect.changed"}:
            continue
        raw_time = event.payload.get("simulated_at")
        value = event.payload.get("valence")
        if (
            not isinstance(raw_time, str)
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
        ):
            continue
        sampled_at = datetime.fromisoformat(raw_time)
        if sampled_at.utcoffset() is not None and sampled_at <= at and -1 <= value <= 1:
            return float(value)
    return 0.0


def _event_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return event.occurred_at
