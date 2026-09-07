"""Turn evidence-linked reflection into a question for later planning, never an action."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent


def reflection_reconsideration_events(
    history: Sequence[DomainEvent], reflection: DomainEvent, simulated_at: datetime
) -> list[DomainEvent]:
    """Raise one bounded planning question when reflection traces to a real setback."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Reflection reconsideration time must be timezone-aware")
    if reflection.kind != "reflection.recorded" or reflection.aggregate_id != "pathos":
        return []
    reconsideration_id = f"reconsider-{reflection.event_id}"
    if any(
        event.kind == "reflection.reconsideration_raised"
        and event.payload.get("reconsideration_id") == reconsideration_id
        for event in history
    ):
        return []
    memory_id = reflection.payload.get("source_memory_id")
    if not isinstance(memory_id, str):
        return []
    memory = next(
        (
            event
            for event in history
            if str(event.event_id) == memory_id
            and event.kind == "memory.recorded"
            and event.aggregate_id == "pathos"
            and event.payload.get("owner", "pathos") == "pathos"
        ),
        None,
    )
    if memory is None or memory.payload.get("category") == "dream":
        return []
    source_id = memory.payload.get("source_event_id")
    if not isinstance(source_id, str):
        return []
    source = next((event for event in history if str(event.event_id) == source_id), None)
    if source is None or source.aggregate_id != "pathos":
        return []
    appraisal = next(
        (
            event
            for event in reversed(history)
            if event.kind == "appraisal.recorded"
            and event.payload.get("source_event_id") == source_id
        ),
        None,
    )
    if appraisal is None or float(appraisal.payload.get("desirability", 0)) > -0.3:
        return []
    target = _planning_target(source, memory)
    if target is None:
        return []
    target_type, target_id = target
    question = {
        "commitment": "Should I repair, renegotiate, or release this commitment?",
        "schedule": "Should I reschedule this activity, change it, or let it go?",
        "goal": "Does this goal still fit, or does it need a different next step?",
    }[target_type]
    return [
        DomainEvent(
            "reflection.reconsideration_raised",
            "pathos",
            {
                "reconsideration_id": reconsideration_id,
                "source_reflection_id": str(reflection.event_id),
                "source_memory_id": memory_id,
                "source_event_id": source_id,
                "target_type": target_type,
                "target_id": target_id,
                "text": question,
                "expires_at": (simulated_at + timedelta(hours=48)).isoformat(),
                "simulated_at": simulated_at.isoformat(),
                "action_authority": False,
            },
            causation_id=reflection.event_id,
            correlation_id=reflection.correlation_id or reconsideration_id,
        )
    ]


def _planning_target(source: DomainEvent, memory: DomainEvent) -> tuple[str, str] | None:
    for target_type, field in (
        ("commitment", "commitment_id"),
        ("schedule", "schedule_id"),
        ("goal", "goal_id"),
    ):
        value = source.payload.get(field, memory.payload.get(field))
        if isinstance(value, str) and value.strip():
            return target_type, value
    return None
