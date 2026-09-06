"""Execute due accepted work, learning, and attendance from linked plans."""

from __future__ import annotations

from datetime import datetime

from eidos.domain.actions import ActionKind, ActionProposal, resolve_action
from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState

SCHEDULED_ACTIONS = {ActionKind.WORK, ActionKind.LEARN, ActionKind.ATTEND}
SCHEDULED_ACTION_VALUES = {action.value for action in SCHEDULED_ACTIONS}


def scheduled_activity_events(
    state: PlanningState,
    *,
    actor_location_id: str,
    simulated_at: datetime,
    actual_revision: int,
) -> list[DomainEvent]:
    """Complete due non-conversation plans and their linked obligations."""

    output: list[DomainEvent] = []
    projected = state
    for entry in state.calendar.values():
        if entry.status != "scheduled" or entry.action not in SCHEDULED_ACTION_VALUES:
            continue
        action = ActionKind(entry.action)
        starts_at = datetime.fromisoformat(entry.starts_at)
        ends_at = datetime.fromisoformat(entry.ends_at) if entry.ends_at else starts_at
        due = starts_at if action is ActionKind.ATTEND else ends_at
        if simulated_at < due or entry.location_id != actor_location_id:
            continue
        if action is ActionKind.ATTEND and simulated_at > ends_at:
            continue
        intention = next(
            (
                item
                for item in projected.intentions.values()
                if item.goal_id == entry.goal_id
                and item.action == action.value
                and item.target_id == entry.target_id
                and item.status == "active"
            ),
            None,
        )
        if intention is None:
            continue
        resolution = resolve_action(
            ActionProposal(
                proposal_id=f"complete-{entry.schedule_id}",
                actor_id="pathos",
                action=action,
                expected_revision=actual_revision + len(output),
                target_id=entry.target_id,
                schedule_id=entry.schedule_id,
                intention_id=intention.intention_id,
            ),
            state=projected,
            actor_location_id=actor_location_id,
            actual_revision=actual_revision + len(output),
            simulated_at=simulated_at,
        )
        output.extend(resolution.events)
        for event in resolution.events:
            projected = projected.apply(event)
        if not resolution.accepted:
            continue
        activity = next(event for event in resolution.events if event.kind == "activity.completed")
        correlation = entry.commitment_id or entry.goal_id or entry.schedule_id

        def consequence(kind: str, payload: dict[str, object]) -> DomainEvent:
            return DomainEvent(
                kind,
                "pathos",
                payload,
                causation_id=activity.event_id,
                correlation_id=correlation,
            )

        if entry.commitment_id is not None:
            fulfilled = consequence(
                "commitment.fulfilled",
                {
                    "commitment_id": entry.commitment_id,
                    "simulated_at": simulated_at.isoformat(),
                },
            )
            output.append(fulfilled)
            projected = projected.apply(fulfilled)
        if entry.goal_id is not None and projected.goals[entry.goal_id].status == "active":
            goal = projected.goals[entry.goal_id]
            if goal.progress >= 1 or entry.commitment_id is not None:
                achieved = consequence(
                    "goal.achieved",
                    {"goal_id": entry.goal_id, "simulated_at": simulated_at.isoformat()},
                )
                output.append(achieved)
                projected = projected.apply(achieved)
        memory = consequence(
            "memory.recorded",
            {
                "text": f"I completed the planned {action.value}: {entry.title}.",
                "owner": "pathos",
                "category": "accomplishment",
                "source": "deterministic-consequence",
                "source_event_id": str(activity.event_id),
                "goal_id": entry.goal_id,
                "location_id": entry.location_id,
                "importance": 0.7,
                "confidence": 1.0,
                "simulated_at": simulated_at.isoformat(),
            },
        )
        output.append(memory)
    return output
