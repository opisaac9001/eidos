"""Turn introduced useful objects into chosen, feasible, resource-backed projects."""

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


def object_opportunity_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    catalog: WorldCatalog,
    planning: PlanningState,
    *,
    curiosity: float,
    mastery: float,
    values: Mapping[str, float],
) -> list[DomainEvent]:
    """Resolve expired object plans, then consider one newly introduced object."""
    expired = _expired_object_plan_events(planning, simulated_at)
    if expired:
        return expired
    considered = {
        str(event.payload["source_registration_id"])
        for event in history
        if event.kind == "object.opportunity_evaluated"
    }
    registration = next(
        (
            event
            for event in history
            if event.kind == "object.registered"
            and (
                event.payload.get("entity_kind") == "object"
                or event.payload.get("source") == "replacement-lifecycle"
            )
            and str(event.event_id) not in considered
        ),
        None,
    )
    if registration is None:
        return []
    object_id = str(registration.payload["object_id"])
    item = planning.objects.get(object_id)
    if (
        item is None
        or item.location_id not in catalog.places
        or item.condition not in {"good", "usable", "repaired"}
    ):
        return []
    windows = feasible_activity_windows(planning, simulated_at, catalog, item.location_id, count=2)
    if len(windows) != 2:
        return []
    curiosity_value = _value(values, "curiosity", 0.5)
    craft_value = _value(values, "craft", 0.5)
    score = max(
        0.1,
        min(
            0.95,
            0.15 + 0.25 * curiosity + 0.2 * mastery + 0.2 * curiosity_value + 0.2 * craft_value,
        ),
    )
    sample = _sample(f"object-opportunity-{object_id}")
    accepted = sample < score
    goal_id = f"use-introduced-{object_id}"
    evaluated = DomainEvent(
        "object.opportunity_evaluated",
        "pathos",
        {
            "source_registration_id": str(registration.event_id),
            "object_id": object_id,
            "decision": "pursue" if accepted else "decline",
            "decision_score": score,
            "decision_sample": sample,
            "decision_curiosity": curiosity,
            "decision_mastery": mastery,
            "reason": (
                "The object fits Pathos's current curiosity, capability, and values."
                if accepted
                else "Pathos chose not to make a project from this object."
            ),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=registration.event_id,
        correlation_id=goal_id,
    )
    if not accepted:
        return [evaluated]
    name = str(registration.payload["name"])
    events: list[DomainEvent] = [
        evaluated,
        DomainEvent(
            "goal.activated",
            "pathos",
            {
                "goal_id": goal_id,
                "title": f"Discover a practical use for {name}",
                "motivation": str(
                    registration.payload.get(
                        "purpose", "Learn what this newly encountered object can support."
                    )
                ),
                "source_registration_id": str(registration.event_id),
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=evaluated.event_id,
            correlation_id=goal_id,
        ),
    ]
    for number, starts_at in enumerate(windows, 1):
        events.append(
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": f"{goal_id}-session-{number}",
                    "title": f"Try {name} in practice",
                    "starts_at": starts_at.isoformat(),
                    "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
                    "location_id": item.location_id,
                    "actor_id": "pathos",
                    "action": ActionKind.ATTEND.value,
                    "target_id": object_id,
                    "resource_id": object_id,
                    "goal_id": goal_id,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=evaluated.event_id,
                correlation_id=goal_id,
            )
        )
    projected = planning
    for event in events:
        projected = projected.apply(event)
    for number in range(1, 3):
        intention = resolve_intention(
            IntentionProposal(
                f"intend-{goal_id}-session-{number}",
                f"{goal_id}-session-{number}-intention",
                "pathos",
                ActionKind.ATTEND,
                f"Learn through direct, bounded use of {name}.",
                0.48,
                len(history) + len(events),
                goal_id=goal_id,
                target_id=object_id,
            ),
            state=projected,
            actual_revision=len(history) + len(events),
            simulated_at=simulated_at,
        )
        events.extend(intention.events)
        for event in intention.events:
            projected = projected.apply(event)
    return events


def borrowed_object_opportunity_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    catalog: WorldCatalog,
    planning: PlanningState,
) -> list[DomainEvent]:
    """Fit actual use of a consented temporary substitute before its return date."""
    handled = {
        str(event.payload["source_loan_id"])
        for event in history
        if event.kind in {"object.loan_use_planned", "object.loan_use_skipped"}
    }
    loan = next(
        (
            event
            for event in history
            if event.kind == "object.recovery_loaned" and str(event.event_id) not in handled
        ),
        None,
    )
    if loan is None:
        return []
    object_id = str(loan.payload["object_id"])
    item = planning.objects.get(object_id)
    due_at = datetime.fromisoformat(str(loan.payload["due_at"]))
    windows = (
        feasible_activity_windows(planning, simulated_at, catalog, item.location_id, count=2)
        if item is not None
        and item.custodian_id == "pathos"
        and item.location_id in catalog.places
        and item.condition in {"good", "usable", "repaired"}
        else []
    )
    windows = [window for window in windows if window + timedelta(hours=1) <= due_at]
    offer_id = str(loan.payload["offer_id"])
    correlation = f"use-borrowed-{offer_id}"
    marker = DomainEvent(
        "object.loan_use_planned" if len(windows) == 2 else "object.loan_use_skipped",
        "pathos",
        {
            "source_loan_id": str(loan.event_id),
            "offer_id": offer_id,
            "object_id": object_id,
            "reason": (
                "Two feasible uses fit before the agreed return time."
                if len(windows) == 2
                else "The temporary loan did not leave two honest use windows."
            ),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=loan.event_id,
        correlation_id=correlation,
    )
    if len(windows) != 2 or item is None:
        return [marker]
    events = [
        marker,
        DomainEvent(
            "goal.activated",
            "pathos",
            {
                "goal_id": correlation,
                "title": f"Use the borrowed {item.name} before returning it",
                "motivation": "Make bounded practical use of a temporary, consented substitute.",
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=marker.event_id,
            correlation_id=correlation,
        ),
    ]
    for number, starts_at in enumerate(windows, 1):
        events.append(
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": f"{correlation}-session-{number}",
                    "title": f"Use borrowed {item.name}",
                    "starts_at": starts_at.isoformat(),
                    "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
                    "location_id": item.location_id,
                    "actor_id": "pathos",
                    "action": ActionKind.ATTEND.value,
                    "target_id": object_id,
                    "resource_id": object_id,
                    "goal_id": correlation,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=marker.event_id,
                correlation_id=correlation,
            )
        )
    projected = planning
    for event in events:
        projected = projected.apply(event)
    for number in range(1, 3):
        intention = resolve_intention(
            IntentionProposal(
                f"intend-{correlation}-session-{number}",
                f"{correlation}-session-{number}-intention",
                "pathos",
                ActionKind.ATTEND,
                f"Use {item.name} within the explicitly limited loan.",
                0.72,
                len(history) + len(events),
                goal_id=correlation,
                target_id=object_id,
            ),
            state=projected,
            actual_revision=len(history) + len(events),
            simulated_at=simulated_at,
        )
        events.extend(intention.events)
        for event in intention.events:
            projected = projected.apply(event)
    return events


def _expired_object_plan_events(
    planning: PlanningState, simulated_at: datetime
) -> list[DomainEvent]:
    output: list[DomainEvent] = []
    projected = planning
    affected_goals: set[str] = set()
    for entry in planning.calendar.values():
        if (
            entry.status != "scheduled"
            or not entry.schedule_id.startswith(("use-introduced-", "use-borrowed-"))
            or entry.ends_at is None
            or datetime.fromisoformat(entry.ends_at) >= simulated_at
        ):
            continue
        failed = DomainEvent(
            "schedule.failed",
            "pathos",
            {
                "schedule_id": entry.schedule_id,
                "reason": "The object-use window passed before valid resource-backed completion.",
                "simulated_at": simulated_at.isoformat(),
            },
            correlation_id=entry.goal_id or entry.schedule_id,
        )
        output.append(failed)
        projected = projected.apply(failed)
        intention = next(
            (
                item
                for item in projected.intentions.values()
                if item.status == "active"
                and item.goal_id == entry.goal_id
                and item.target_id == entry.target_id
            ),
            None,
        )
        if intention is not None:
            abandoned = DomainEvent(
                "intention.abandoned",
                "pathos",
                {
                    "intention_id": intention.intention_id,
                    "reason": "The linked object-use session expired.",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=failed.event_id,
                correlation_id=entry.goal_id or entry.schedule_id,
            )
            output.append(abandoned)
            projected = projected.apply(abandoned)
        if entry.goal_id is not None:
            affected_goals.add(entry.goal_id)
    for goal_id in sorted(affected_goals):
        if (
            projected.goals[goal_id].status == "active"
            and not any(
                entry.goal_id == goal_id and entry.status in {"scheduled", "interrupted"}
                for entry in projected.calendar.values()
            )
            and not any(
                intention.goal_id == goal_id and intention.status == "active"
                for intention in projected.intentions.values()
            )
        ):
            abandoned = DomainEvent(
                "goal.abandoned",
                "pathos",
                {
                    "goal_id": goal_id,
                    "reason": "The introduced object was not available during either planned use.",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=output[-1].event_id,
                correlation_id=goal_id,
            )
            output.append(abandoned)
            projected = projected.apply(abandoned)
    return output


def _value(values: Mapping[str, float], key: str, default: float) -> float:
    value = values.get(key, default)
    return max(0.0, min(1.0, float(value)))


def _sample(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
