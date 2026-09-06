"""Persist bounded drift after Pathos actually uses an imperfect recollection."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Sequence

from eidos.application.memory import RecalledMemory
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
    already_used = {
        str(event.causation_id)
        for event in history
        if event.kind == "memory.reconsolidated" and event.causation_id is not None
    }
    for item in recalled:
        if item.detail_level not in {"partial", "vague"}:
            continue
        memory_id = str(item.event.event_id)
        prior = state.latest.get(memory_id)
        if prior is not None and at - prior.changed_at < _COOLDOWN:
            continue
        access = next(
            (
                event
                for event in reversed(history)
                if event.kind == "memory.accessed"
                and event.payload.get("memory_id") == memory_id
                and str(event.event_id) not in already_used
            ),
            None,
        )
        if access is None:
            continue
        revision = prior.revision + 1 if prior else 1
        source_confidence = float(item.event.payload.get("confidence", 1.0))
        confidence = min(
            prior.confidence if prior else source_confidence,
            max(0.15, item.accessibility * (0.94**revision)),
        )
        output.append(
            DomainEvent(
                "memory.reconsolidated",
                "pathos",
                {
                    "memory_id": memory_id,
                    "revision": revision,
                    "recalled_text": _drift_text(
                        item.recalled_text, item.detail_level, revision, affective_bias
                    ),
                    "confidence": round(confidence, 4),
                    "detail_level": item.detail_level,
                    "affective_bias": round(affective_bias, 4),
                    "drift_kind": "gist_only" if item.detail_level == "vague" else "detail_loss",
                    "epistemic_status": "subjective_recollection",
                    "simulated_at": at.isoformat(),
                },
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


def _drift_text(text: str, detail_level: str, revision: int, affective_bias: float) -> str:
    clause = re.split(r"[,;.!?]", text, maxsplit=1)[0].strip()
    clause = re.sub(r"^I remember\s+", "", clause, flags=re.IGNORECASE).strip()
    if detail_level == "vague":
        drifted = f"Something about {clause.lower()} still feels familiar, but I cannot place it."
    elif revision % 2:
        drifted = f"I mostly remember {clause.lower()}, though I may be missing the context."
    else:
        drifted = f"I think {clause.lower()}, but the surrounding details no longer feel reliable."
    if affective_bias <= -0.25:
        return f"{drifted} It feels heavier to me now."
    if affective_bias >= 0.25:
        return f"{drifted} It feels warmer to me now."
    return drifted


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
