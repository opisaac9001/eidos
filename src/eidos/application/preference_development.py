"""Turn repeated voluntary behavior into slow, bounded preference changes."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.identity import DEFAULT_PREFERENCES, project_identity
from eidos.domain.preferences import preference_dimensions

MAX_LEARNED_PREFERENCES = 5
EMERGENCE_COOLDOWN = timedelta(days=14)
EVIDENCE_SPAN = timedelta(days=7)
RETIRE_AFTER = timedelta(days=120)


def preference_development_events(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> list[DomainEvent]:
    """Emit at most one evidence-backed emergence or retirement at the evening review."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Preference review time must be timezone-aware")
    if simulated_at.hour != 20:
        return []
    identity = project_identity(history)
    emergence_events = [event for event in history if event.kind == "preference.emerged"]
    retirement_events = [event for event in history if event.kind == "preference.retired"]
    latest_change = next(
        (
            _event_time(event)
            for event in reversed(history)
            if event.kind in {"preference.emerged", "preference.retired"}
        ),
        None,
    )
    if latest_change is not None and simulated_at - latest_change < EMERGENCE_COOLDOWN:
        return []
    active_ids = {
        str(event.payload["preference_id"])
        for event in emergence_events
        if not any(
            retired.payload.get("preference_id") == event.payload.get("preference_id")
            and history.index(retired) > history.index(event)
            for retired in retirement_events
        )
    }
    learned_count = len(identity.preferences) - len(DEFAULT_PREFERENCES)
    evidence: dict[str, list[tuple[DomainEvent, str]]] = defaultdict(list)
    for event in history:
        for preference_id, label in preference_dimensions(event):
            evidence[preference_id].append((event, label))
    if learned_count < MAX_LEARNED_PREFERENCES:
        candidates: list[tuple[int, str, str, list[DomainEvent]]] = []
        for preference_id, records in evidence.items():
            if preference_id in active_ids:
                continue
            latest_retired = next(
                (
                    event
                    for event in reversed(retirement_events)
                    if event.payload.get("preference_id") == preference_id
                ),
                None,
            )
            sources = [
                event
                for event, _ in records
                if latest_retired is None or _event_time(event) > _event_time(latest_retired)
            ]
            if (
                len(sources) < 3
                or _event_time(sources[-1]) - _event_time(sources[0]) < EVIDENCE_SPAN
            ):
                continue
            candidates.append((len(sources), preference_id, records[-1][1], sources))
        if candidates:
            _, preference_id, label, sources = max(candidates, key=lambda item: (item[0], item[1]))
            selected = sources if len(sources) <= 5 else [sources[0], *sources[-4:]]
            return [
                DomainEvent(
                    "preference.emerged",
                    "pathos",
                    {
                        "preference_id": preference_id,
                        "label": label,
                        **{
                            f"source_event_{position}": (
                                str(selected[position - 1].event_id)
                                if position <= len(selected)
                                else None
                            )
                            for position in range(1, 6)
                        },
                        "evidence_count": len(sources),
                        "first_evidence_at": _event_time(sources[0]).isoformat(),
                        "simulated_at": simulated_at.isoformat(),
                        "owner": "pathos",
                    },
                    causation_id=selected[-1].event_id,
                    correlation_id=f"preference-{preference_id}",
                )
            ]
    for emerged in emergence_events:
        preference_id = str(emerged.payload.get("preference_id", ""))
        if preference_id not in active_ids:
            continue
        later_sources = [
            event
            for event, _ in evidence.get(preference_id, [])
            if _event_time(event) > _event_time(emerged)
        ]
        last_support = _event_time(later_sources[-1]) if later_sources else _event_time(emerged)
        if simulated_at - last_support >= RETIRE_AFTER:
            return [
                DomainEvent(
                    "preference.retired",
                    "pathos",
                    {
                        "preference_id": preference_id,
                        "label": emerged.payload["label"],
                        "reason": "No supporting voluntary behavior recurred for 120 simulated days.",
                        "source_emergence_id": str(emerged.event_id),
                        "simulated_at": simulated_at.isoformat(),
                        "owner": "pathos",
                    },
                    causation_id=emerged.event_id,
                    correlation_id=f"preference-{preference_id}",
                )
            ]
    return []


def _event_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if not isinstance(value, str):
        raise ValueError("Preference evidence needs simulated time")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Preference evidence time must be timezone-aware")
    return parsed
