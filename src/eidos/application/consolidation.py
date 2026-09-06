"""Source-linked daily memory themes that never replace episodic evidence."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent


def consolidation_events(
    history: Sequence[DomainEvent], simulated_at: datetime, max_themes: int = 5
) -> list[DomainEvent]:
    if not 1 <= max_themes <= 20:
        raise ValueError("max_themes must be between 1 and 20")
    day = (simulated_at - timedelta(days=1)).date()
    existing = {
        str(event.payload["consolidation_id"])
        for event in history
        if event.kind == "memory.consolidated"
    }
    groups: dict[tuple[str, str, str], list[DomainEvent]] = defaultdict(list)
    for event in history:
        if event.kind != "memory.recorded" or _simulated_date(event) != day:
            continue
        owner = event.payload.get("owner", "pathos")
        if not isinstance(owner, str):
            continue
        if isinstance(event.payload.get("goal_id"), str):
            theme_type, theme_id = "goal", str(event.payload["goal_id"])
        elif isinstance(event.payload.get("person_id"), str):
            theme_type, theme_id = "person", str(event.payload["person_id"])
        else:
            theme_type, theme_id = "category", str(event.payload.get("category", "experience"))
        groups[(owner, theme_type, theme_id)].append(event)
    candidates = sorted(
        ((key, values) for key, values in groups.items() if len(values) >= 2),
        key=lambda item: (-len(item[1]), item[0]),
    )[:max_themes]
    output: list[DomainEvent] = []
    for (owner, theme_type, theme_id), sources in candidates:
        consolidation_id = f"{day.isoformat()}:{owner}:{theme_type}:{theme_id}"
        if consolidation_id in existing:
            continue
        dream_only = all(source.payload.get("category") == "dream" for source in sources)
        confidence = min(float(source.payload.get("confidence", 1.0)) for source in sources)
        summary = DomainEvent(
            "memory.consolidated",
            "pathos",
            {
                "consolidation_id": consolidation_id,
                "owner": owner,
                "theme_type": theme_type,
                "theme_id": theme_id,
                "source_count": len(sources),
                "source_first_id": str(sources[0].event_id),
                "source_last_id": str(sources[-1].event_id),
                "confidence": confidence,
                "dream_only": dream_only,
                "text": f"{len(sources)} source memories from {day.isoformat()} share the {theme_type} theme {theme_id}.",
                "simulated_at": simulated_at.isoformat(),
            },
            correlation_id=consolidation_id,
        )
        output.append(summary)
        output.extend(
            DomainEvent(
                "memory.consolidation_member",
                "pathos",
                {
                    "consolidation_id": consolidation_id,
                    "source_memory_id": str(source.event_id),
                    "owner": owner,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=summary.event_id,
                correlation_id=consolidation_id,
            )
            for source in sources
        )
    return output


def _simulated_date(event: DomainEvent) -> date:
    value = event.payload.get("simulated_at")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    return event.occurred_at.date()
