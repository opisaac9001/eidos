"""Source-linked daily memory themes that never replace episodic evidence."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from eidos.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class ConsolidationIndex:
    memories_by_day: Mapping[str, tuple[DomainEvent, ...]]
    memory_ids: tuple[str, ...]
    consolidation_ids: frozenset[str]
    revision: int

    @classmethod
    def build(
        cls,
        history: list[DomainEvent],
        *,
        base_index: ConsolidationIndex | None = None,
        materialized_state: Mapping[str, Any] | None = None,
        materialized_revision: int = 0,
    ) -> ConsolidationIndex:
        if base_index is not None and materialized_state is not None:
            raise ValueError("Choose one consolidation index base")
        if base_index is not None:
            materialized_revision = base_index.revision
        if not 0 <= materialized_revision <= len(history):
            raise ValueError("Consolidation revision is outside supplied history")
        if base_index is not None:
            groups = {day: list(events) for day, events in base_index.memories_by_day.items()}
            memory_ids = list(base_index.memory_ids)
            existing = set(base_index.consolidation_ids)
        elif materialized_state is not None:
            prefix = history[:materialized_revision]
            if materialized_state.get("schema") != 1:
                raise ValueError("Unsupported consolidation index schema")
            raw_memory_ids = _string_list(materialized_state.get("memory_ids"))
            raw_consolidation_ids = _string_list(materialized_state.get("consolidation_ids"))
            expected_memories = [event for event in prefix if event.kind == "memory.recorded"]
            expected_consolidations = [
                str(event.payload["consolidation_id"])
                for event in prefix
                if event.kind == "memory.consolidated"
            ]
            if raw_memory_ids != [str(event.event_id) for event in expected_memories]:
                raise ValueError("Materialized consolidation memories do not match history")
            if raw_consolidation_ids != sorted(expected_consolidations):
                raise ValueError("Materialized consolidation IDs do not match history")
            groups = defaultdict(list)
            for event in expected_memories:
                groups[_simulated_date(event).isoformat()].append(event)
            memory_ids = raw_memory_ids
            existing = set(raw_consolidation_ids)
        else:
            groups = defaultdict(list)
            memory_ids = []
            existing = set()
            materialized_revision = 0
        known_memory_ids = set(memory_ids)
        for event in history[materialized_revision:]:
            if event.kind == "memory.recorded":
                event_id = str(event.event_id)
                if event_id in known_memory_ids:
                    raise ValueError("Consolidation index contains a duplicate memory")
                groups.setdefault(_simulated_date(event).isoformat(), []).append(event)
                memory_ids.append(event_id)
                known_memory_ids.add(event_id)
            elif event.kind == "memory.consolidated":
                consolidation_id = event.payload.get("consolidation_id")
                if not isinstance(consolidation_id, str) or not consolidation_id.strip():
                    raise ValueError("Consolidation event requires an ID")
                existing.add(consolidation_id)
        return cls(
            MappingProxyType({day: tuple(events) for day, events in groups.items()}),
            tuple(memory_ids),
            frozenset(existing),
            len(history),
        )

    def materialized_state(self) -> Mapping[str, Any]:
        return {
            "schema": 1,
            "memory_ids": list(self.memory_ids),
            "consolidation_ids": sorted(self.consolidation_ids),
        }


def consolidation_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    max_themes: int = 5,
    *,
    index: ConsolidationIndex | None = None,
) -> list[DomainEvent]:
    if not 1 <= max_themes <= 20:
        raise ValueError("max_themes must be between 1 and 20")
    day = (simulated_at - timedelta(days=1)).date()
    index = index or ConsolidationIndex.build(list(history))
    if index.revision != len(history):
        raise ValueError("Consolidation index revision does not match history")
    existing = index.consolidation_ids
    groups: dict[tuple[str, str, str], list[DomainEvent]] = defaultdict(list)
    for event in index.memories_by_day.get(day.isoformat(), ()):
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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError("Materialized consolidation IDs must be strings")
    return list(value)
