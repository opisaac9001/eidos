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
                    "recalled_text": _drift_text(item.recalled_text, item.detail_level, revision),
                    "confidence": round(confidence, 4),
                    "detail_level": item.detail_level,
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


def _drift_text(text: str, detail_level: str, revision: int) -> str:
    clause = re.split(r"[,;.!?]", text, maxsplit=1)[0].strip()
    clause = re.sub(r"^I remember\s+", "", clause, flags=re.IGNORECASE).strip()
    if detail_level == "vague":
        return f"Something about {clause.lower()} still feels familiar, but I cannot place it."
    if revision % 2:
        return f"I mostly remember {clause.lower()}, though I may be missing the context."
    return f"I think {clause.lower()}, but the surrounding details no longer feel reliable."
