"""Small shared helpers for Life's cognition contexts and read models."""

from datetime import datetime
from typing import Any, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.self_concept import project_self_concepts
from eidos.domain.semantic_memory import project_semantic_expectations


def latest_weather(history: list[DomainEvent]) -> str:
    return next(
        (
            str(event.payload["text"])
            for event in reversed(history)
            if event.kind == "world.weather" and "text" in event.payload
        ),
        "Clear",
    )


def mood_name(energy: float, valence: float, arousal: float = 0.35) -> str:
    if energy < 0.3:
        return "Sleepy"
    if arousal > 0.65:
        return "Animated" if valence >= 0 else "Tense"
    return "Content" if valence > 0.15 else "Reflective" if valence < -0.1 else "Quietly curious"


def semantic_expectation_context(events: Sequence[DomainEvent]) -> list[dict[str, object]]:
    """Expose Pathos's fallible generalizations without operator-only source metadata."""
    return [
        {
            "text": item.text,
            "subject_id": item.subject_id,
            "predicate": item.predicate,
            "object_value": item.object_value,
            "confidence": item.confidence,
            "epistemic_status": "subjective_generalization",
        }
        for item in project_semantic_expectations(events).expectations.values()
    ]


def self_concept_context(events: Sequence[DomainEvent]) -> list[dict[str, object]]:
    """Expose Pathos's current self-story without its operator-only evidence ledger."""
    return [
        {
            "text": item.text,
            "dimension": item.dimension,
            "stance": item.stance,
            "confidence": item.confidence,
            "epistemic_status": "subjective_self_interpretation",
        }
        for item in project_self_concepts(events).concepts.values()
    ]


def vars_for(value: Any) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name in value.__dataclass_fields__:
        item = getattr(value, name)
        output[name] = item.isoformat() if isinstance(item, datetime) else item
    return output
