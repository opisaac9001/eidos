"""Form a cautious autobiographical interpretation from Pathos's own outcomes."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.self_concept import (
    follow_through_direction,
    project_self_concepts,
    self_concept_confidence,
    self_concept_stance,
    self_concept_text,
)

REVIEW_WINDOW = timedelta(days=60)
REVISION_COOLDOWN = timedelta(days=14)


def self_concept_events(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    if at.utcoffset() is None:
        raise ValueError("Self-concept review time must be timezone-aware")
    if at.hour != 21:
        return []
    by_day: dict[str, tuple[DomainEvent, int, datetime]] = {}
    for event in history:
        direction = follow_through_direction(event)
        if direction is None:
            continue
        source_time = _event_time(event)
        if source_time > at or at - source_time > REVIEW_WINDOW:
            continue
        day = source_time.date().isoformat()
        day_prior = by_day.get(day)
        candidate = (event, direction, source_time)
        if day_prior is None or (abs(direction), str(event.event_id)) > (
            abs(day_prior[1]),
            str(day_prior[0].event_id),
        ):
            by_day[day] = candidate
    sources = sorted(by_day.values(), key=lambda item: (item[2], str(item[0].event_id)))[-8:]
    if len(sources) < 3 or sources[-1][2] - sources[0][2] < timedelta(days=7):
        return []
    concept_id = "pathos-self-concept:follow_through"
    concept_prior = project_self_concepts(history).concepts.get(concept_id)
    source_ids = tuple(str(item[0].event_id) for item in sources)
    if concept_prior is not None:
        if (
            concept_prior.source_event_ids == source_ids
            or at - concept_prior.updated_at < REVISION_COOLDOWN
        ):
            return []
        if not set(source_ids) - set(concept_prior.source_event_ids):
            return []
    directions = [item[1] for item in sources]
    stance = self_concept_stance(directions)
    kind = (
        "self_concept.formed"
        if concept_prior is None
        else "self_concept.reinforced"
        if concept_prior.stance == stance
        else "self_concept.revised"
    )
    return [
        DomainEvent(
            kind,
            "pathos",
            {
                "concept_id": concept_id,
                "revision": concept_prior.revision + 1 if concept_prior is not None else 1,
                "dimension": "follow_through",
                "stance": stance,
                "text": self_concept_text(stance),
                "confidence": self_concept_confidence(
                    directions, (sources[-1][2].date() - sources[0][2].date()).days
                ),
                "positive_count": sum(direction > 0 for direction in directions),
                "negative_count": sum(direction < 0 for direction in directions),
                "source_count": len(sources),
                **{
                    f"source_event_{position}": str(source[0].event_id)
                    for position, source in enumerate(sources, 1)
                },
                "epistemic_status": "subjective_self_interpretation",
                "simulated_at": at.isoformat(),
            },
            causation_id=sources[-1][0].event_id,
            correlation_id=concept_id,
        )
    ]


def _event_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value)
    else:
        parsed = event.occurred_at
    if parsed.utcoffset() is None:
        raise ValueError("Self-concept evidence time must be timezone-aware")
    return parsed
