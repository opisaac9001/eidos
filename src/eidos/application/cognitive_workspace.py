"""Build a small, private blackboard through which Pathos's faculties communicate."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from eidos.application.inner_life import active_concerns, active_dream_inspirations
from eidos.domain.events import DomainEvent


def cognitive_workspace(
    history: Sequence[DomainEvent], simulated_at: datetime, *, limit: int = 12
) -> list[dict[str, object]]:
    """Return bounded subjective material without promoting it to fact or action."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Cognitive workspace time must be timezone-aware")
    if not 1 <= limit <= 32:
        raise ValueError("Cognitive workspace limit must be between one and 32")

    candidates: list[tuple[float, datetime, dict[str, object]]] = []
    specs = {
        "thought.recorded": ("murmur", "inner_monologue", timedelta(hours=6), 0.62),
        "association.formed": ("murmur", "association", timedelta(hours=24), 0.68),
        "reflection.recorded": (
            "reflection",
            "subjective_interpretation",
            timedelta(days=3),
            0.72,
        ),
        "reflection.reconsideration_raised": (
            "reflection",
            "planning_question",
            timedelta(hours=48),
            0.82,
        ),
        "dream.recalled": ("oneiros", "dream_fragment", timedelta(hours=24), 0.55),
    }
    for event in history:
        if event.aggregate_id != "pathos" or event.kind not in specs:
            continue
        created_at = _event_time(event)
        if created_at is None or created_at > simulated_at:
            continue
        faculty, epistemic_status, lifetime, default_salience = specs[event.kind]
        if simulated_at - created_at > lifetime:
            continue
        content = event.payload.get("text")
        if not isinstance(content, str) or not content.strip():
            continue
        salience_value = event.payload.get("salience", default_salience)
        salience = (
            float(salience_value)
            if isinstance(salience_value, (int, float)) and not isinstance(salience_value, bool)
            else default_salience
        )
        candidate = _candidate(
            event,
            faculty,
            event.kind,
            content,
            epistemic_status,
            max(0.0, min(1.0, salience)),
            created_at,
            simulated_at,
        )
        if event.kind == "reflection.reconsideration_raised":
            candidate[2]["target_type"] = event.payload.get("target_type")
            candidate[2]["target_id"] = event.payload.get("target_id")
        candidates.append(candidate)

    for event in history:
        if event.aggregate_id != "pathos" or event.kind != "mind.layer_pulsed":
            continue
        created_at = _event_time(event)
        if (
            created_at is None
            or created_at > simulated_at
            or simulated_at - created_at > timedelta(hours=2)
        ):
            continue
        content = event.payload.get("focus_text")
        layer = event.payload.get("layer")
        activation = event.payload.get("activation")
        if not isinstance(content, str) or not isinstance(layer, str):
            continue
        salience = (
            float(activation)
            if isinstance(activation, (int, float)) and not isinstance(activation, bool)
            else 0.5
        )
        candidates.append(
            _candidate(
                event,
                layer,
                "attention_signal",
                content,
                "attention_not_evidence",
                max(0.0, min(1.0, salience)),
                created_at,
                simulated_at,
            )
        )

    pathos_history = [event for event in history if event.aggregate_id == "pathos"]
    for concern in active_concerns(pathos_history):
        created_at = _event_time(concern)
        content = concern.payload.get("text")
        if created_at is None or created_at > simulated_at or not isinstance(content, str):
            continue
        candidates.append(
            _candidate(
                concern,
                "deliberative",
                "unresolved_concern",
                content,
                "subjective_concern",
                0.88,
                created_at,
                simulated_at,
            )
        )

    inspiration_events = {
        str(event.payload.get("source_dream_id")): event
        for event in history
        if event.aggregate_id == "pathos" and event.kind == "dream.inspiration_considered"
    }
    for inspiration in active_dream_inspirations(history, simulated_at):
        source = inspiration_events.get(inspiration.source_dream_id)
        if source is None:
            continue
        created_at = _event_time(source)
        if created_at is None:
            continue
        candidate = _candidate(
            source,
            "oneiros",
            "dream_inspiration",
            inspiration.suggestion,
            "fiction_sourced_possibility",
            0.58,
            created_at,
            simulated_at,
        )
        candidate[2]["source_dream_id"] = inspiration.source_dream_id
        candidate[2]["motif"] = inspiration.motif
        candidates.append(candidate)

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected: list[dict[str, object]] = []
    faculty_counts: dict[str, int] = {}
    for _, _, item in candidates:
        faculty = str(item["from_faculty"])
        if faculty_counts.get(faculty, 0) >= 3:
            continue
        faculty_counts[faculty] = faculty_counts.get(faculty, 0) + 1
        selected.append(item)
        if len(selected) == limit:
            break
    live_dream = next(
        (item for _, _, item in candidates if item.get("kind") == "dream_inspiration"), None
    )
    if (
        limit >= 4
        and live_dream is not None
        and not any(item.get("kind") == "dream_inspiration" for item in selected)
    ):
        oneiros_index = next(
            (
                index
                for index in range(len(selected) - 1, -1, -1)
                if selected[index].get("from_faculty") == "oneiros"
            ),
            None,
        )
        if oneiros_index is not None:
            selected[oneiros_index] = live_dream
        elif len(selected) == limit:
            selected[-1] = live_dream
        else:
            selected.append(live_dream)
    return selected


def _candidate(
    event: DomainEvent,
    faculty: str,
    kind: str,
    content: str,
    epistemic_status: str,
    salience: float,
    created_at: datetime,
    simulated_at: datetime,
) -> tuple[float, datetime, dict[str, object]]:
    return (
        salience,
        created_at,
        {
            "source_event_id": str(event.event_id),
            "from_faculty": faculty,
            "kind": kind,
            "content": content.strip(),
            "salience": round(salience, 3),
            "age_minutes": max(0, round((simulated_at - created_at).total_seconds() / 60)),
            "epistemic_status": epistemic_status,
            "action_authority": False,
        },
    )


def _event_time(event: DomainEvent) -> datetime | None:
    value = event.payload.get("simulated_at")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.utcoffset() is not None else None
