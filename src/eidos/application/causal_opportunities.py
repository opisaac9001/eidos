"""Wake a decision from a fresh cause, not a date in an authored itinerary."""

from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent


def fresh_cause(
    history: Sequence[DomainEvent],
    now: datetime,
    kinds: frozenset[str],
) -> DomainEvent | None:
    """Newest eligible cause only; never drain stale incidents into new stories."""
    if now.utcoffset() is None:
        raise ValueError("Decision time must be timezone-aware")
    for event in reversed(history):
        if event.kind not in kinds:
            continue
        try:
            at = datetime.fromisoformat(str(event.payload.get("simulated_at")))
        except ValueError:
            continue
        if event.kind == "thought.recorded":
            if event.aggregate_id != "pathos" or event.payload.get("owner", "pathos") != "pathos":
                continue
            if at.utcoffset() is None or now - at >= timedelta(minutes=30):
                continue
        if at.utcoffset() is not None and timedelta(0) <= now - at <= timedelta(hours=1):
            return event
    return None


def optional_schema(candidate_schema: Mapping[str, object]) -> dict[str, object]:
    """A valid thought or world update can end without creating an activity."""
    return {
        "anyOf": [
            candidate_schema,
            {
                "type": "object",
                "properties": {"no_change": {"const": True}},
                "required": ["no_change"],
                "additionalProperties": False,
            },
        ]
    }
