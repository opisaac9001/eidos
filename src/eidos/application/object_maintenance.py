"""Turn repeated introduced-object use into wear and feasible maintenance work."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.application.world_exploration import feasible_activity_windows
from eidos.domain.actions import ActionKind
from eidos.domain.events import DomainEvent
from eidos.domain.intentions import IntentionProposal, resolve_intention
from eidos.domain.planning import PlanningState
from eidos.domain.world_catalog import WorldCatalog


def object_maintenance_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    planning: PlanningState,
    catalog: WorldCatalog,
    *,
    mastery: float,
    values: Mapping[str, float],
) -> list[DomainEvent]:
    """Wear an introduced object, then choose repair or retirement."""
    registrations = {
        str(event.payload["object_id"]): event
        for event in history
        if event.kind == "object.registered"
        and (
            event.payload.get("entity_kind") == "object"
            or event.payload.get("source") == "replacement-lifecycle"
        )
    }
    maintained = {
        str(event.payload["object_id"])
        for event in history
        if event.kind == "object.maintenance_required"
    }
    for object_id, registration in registrations.items():
        item = planning.objects.get(object_id)
        uses = [
            event
            for event in history
            if event.kind == "object.used" and event.payload.get("object_id") == object_id
        ]
        if (
            object_id in maintained
            or item is None
            or item.condition not in {"good", "usable", "repaired"}
            or len(uses) < 2
            or item.location_id not in catalog.places
        ):
            continue
        correlation = f"maintain-introduced-{object_id}"
        required = DomainEvent(
            "object.maintenance_required",
            "pathos",
            {
                "object_id": object_id,
                "source_registration_id": str(registration.event_id),
                "source_use_id": str(uses[-1].event_id),
                "use_count": len(uses),
                "reason": "Repeated practical use exposed wear that now needs attention.",
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=uses[-1].event_id,
            correlation_id=correlation,
        )
        worn = DomainEvent(
            "object.condition_changed",
            "pathos",
            {
                "object_id": object_id,
                "condition": "broken",
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=required.event_id,
            correlation_id=correlation,
        )
        windows = feasible_activity_windows(
            planning, simulated_at, catalog, item.location_id, count=2
        )
        craft = max(0.0, min(1.0, float(values.get("craft", 0.5))))
        care = max(0.0, min(1.0, float(values.get("care", 0.5))))
        score = max(0.1, min(0.9, 0.2 + 0.3 * mastery + 0.25 * craft + 0.15 * care))
        sample = _sample(f"maintenance-choice-{object_id}")
        repair = len(windows) == 2 and sample < score
        decision = DomainEvent(
            "object.maintenance_decided",
            "pathos",
            {
                "object_id": object_id,
                "decision": "repair" if repair else "retire",
                "decision_score": score,
                "decision_sample": sample,
                "feasible_windows": len(windows),
                "reason": (
                    "Pathos judged the worn object worth a bounded repair attempt."
                    if repair
                    else "Pathos chose not to commit scarce time and capability to this repair."
                ),
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=worn.event_id,
            correlation_id=correlation,
        )
        if not repair:
            retired = DomainEvent(
                "object.condition_changed",
                "pathos",
                {
                    "object_id": object_id,
                    "condition": "retired",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=decision.event_id,
                correlation_id=correlation,
            )
            return [required, worn, decision, retired]
        name = item.name
        events = [
            required,
            worn,
            decision,
            DomainEvent(
                "goal.activated",
                "pathos",
                {
                    "goal_id": correlation,
                    "title": f"Restore {name} after wear",
                    "motivation": "Care for a useful shared object instead of treating it as disposable.",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=decision.event_id,
                correlation_id=correlation,
            ),
        ]
        actions = (ActionKind.ATTEND, ActionKind.REPAIR)
        titles = (f"Inspect the wear on {name}", f"Repair {name}")
        for number, (starts_at, action, title) in enumerate(zip(windows, actions, titles), 1):
            events.append(
                DomainEvent(
                    "schedule.created",
                    "pathos",
                    {
                        "schedule_id": f"{correlation}-session-{number}",
                        "title": title,
                        "starts_at": starts_at.isoformat(),
                        "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
                        "location_id": item.location_id,
                        "actor_id": "pathos",
                        "action": action.value,
                        "target_id": object_id,
                        "goal_id": correlation,
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=decision.event_id,
                    correlation_id=correlation,
                )
            )
        projected = planning
        for event in events:
            projected = projected.apply(event)
        for number, action in enumerate(actions, 1):
            resolution = resolve_intention(
                IntentionProposal(
                    f"intend-{correlation}-session-{number}",
                    f"{correlation}-session-{number}-intention",
                    "pathos",
                    action,
                    "Inspect and restore a shared object changed by actual use.",
                    0.62,
                    len(history) + len(events),
                    goal_id=correlation,
                    target_id=object_id,
                ),
                state=projected,
                actual_revision=len(history) + len(events),
                simulated_at=simulated_at,
            )
            events.extend(resolution.events)
            for event in resolution.events:
                projected = projected.apply(event)
        return events
    return []


def _sample(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
