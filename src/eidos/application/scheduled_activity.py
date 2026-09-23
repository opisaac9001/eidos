"""Execute due accepted work, learning, and attendance from linked plans."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from typing import Mapping, Sequence
from uuid import UUID

from eidos.application.activity_execution import activity_effort
from eidos.application.nourishment import nourishment_events, planned_meal_kind
from eidos.domain.actions import ActionKind, ActionProposal, resolve_action
from eidos.domain.events import DomainEvent
from eidos.domain.planning import CalendarEntry, PlanningState
from eidos.domain.state import PathosState

SCHEDULED_ACTIONS = {ActionKind.WORK, ActionKind.LEARN, ActionKind.ATTEND, ActionKind.REPAIR}
SCHEDULED_ACTION_VALUES = {action.value for action in SCHEDULED_ACTIONS}


def scheduled_activity_events(
    state: PlanningState,
    *,
    actor_location_id: str,
    simulated_at: datetime,
    actual_revision: int,
    repair_mastery: float = 1.0,
    actor_locations: Mapping[str, str] | None = None,
    cognitive_history: Sequence[DomainEvent] = (),
    cognitive_capacity: float = 1.0,
    require_execution_evidence: bool = False,
    actor_state: PathosState | None = None,
    available_pence: int | None = None,
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
        due = (
            ends_at
            if entry.activity_type is not None
            else (starts_at if action is ActionKind.ATTEND else ends_at)
        )
        effort = (
            activity_effort(cognitive_history, entry, simulated_at)
            if require_execution_evidence
            else None
        )
        if simulated_at < due and not (effort is not None and effort["ready"]):
            continue
        intention = next(
            (
                item
                for item in projected.intentions.values()
                if (entry.intention_id is None or item.intention_id == entry.intention_id)
                and item.goal_id == entry.goal_id
                and item.action == action.value
                and item.target_id == entry.target_id
                and item.status == "active"
            ),
            None,
        )
        if intention is None:
            continue
        if require_execution_evidence:
            assert effort is not None
            if not effort["ready"]:
                if simulated_at >= ends_at:
                    unfinished = next(
                        (
                            e
                            for e in reversed(cognitive_history)
                            if e.kind == "activity.execution_unfinished"
                            and e.payload.get("schedule_id") == entry.schedule_id
                        ),
                        None,
                    )
                    # Losing a work window does not erase the desire, abandon the
                    # whole project, or discharge a promise. A new window requires
                    # a separate choice; the partial effort remains in history.
                    missed = [
                        DomainEvent(
                            "schedule.interrupted",
                            "pathos",
                            {
                                "schedule_id": entry.schedule_id,
                                "reason": "The reserved time ended without enough actual activity; unfinished work remains recorded.",
                                "simulated_at": simulated_at.isoformat(),
                            },
                            causation_id=unfinished.event_id if unfinished else None,
                            correlation_id=entry.schedule_id,
                        )
                    ]
                    output.extend(missed)
                    for event in missed:
                        projected = projected.apply(event)
                continue
        if prospective_memory_lapse(
            entry,
            intention.priority,
            cognitive_history,
            cognitive_capacity=cognitive_capacity,
        ):
            lapse = DomainEvent(
                "prospective_memory.lapsed",
                "pathos",
                {
                    "schedule_id": entry.schedule_id,
                    "intention_id": intention.intention_id,
                    "reason": "A low-priority personal plan slipped Pathos's mind.",
                    "simulated_at": simulated_at.isoformat(),
                },
                correlation_id=entry.source_proposal_id or entry.schedule_id,
            )
            missed_events = _failed_open_plan_events(
                projected,
                entry,
                intention.intention_id,
                str(lapse.payload["reason"]),
                simulated_at,
                causation_id=lapse.event_id,
            )
            output.extend((lapse, *missed_events))
            for event in missed_events:
                projected = projected.apply(event)
            continue
        if entry.location_id != actor_location_id or (
            action is ActionKind.ATTEND and simulated_at > ends_at
        ):
            if entry.activity_type is not None and simulated_at > ends_at:
                missed_events = _failed_open_plan_events(
                    projected,
                    entry,
                    intention.intention_id,
                    "Pathos was not able to be at the planned place in time.",
                    simulated_at,
                )
                output.extend(missed_events)
                for event in missed_events:
                    projected = projected.apply(event)
            continue
        if entry.companion_id is not None and (
            actor_locations is None or actor_locations.get(entry.companion_id) != entry.location_id
        ):
            companion_consequences = _failed_open_plan_events(
                projected,
                entry,
                intention.intention_id,
                "The hoped-for companion was not present when the activity was due.",
                simulated_at,
            )
            output.extend(companion_consequences)
            for event in companion_consequences:
                projected = projected.apply(event)
            continue
        meal_kind = planned_meal_kind(entry)
        meal_consequences: list[DomainEvent] = []
        if meal_kind is not None:
            if actor_state is None or available_pence is None:
                reason = "The meal could not be verified against his body and available food."
                failed = _failed_open_plan_events(
                    projected,
                    entry,
                    intention.intention_id,
                    reason,
                    simulated_at,
                )
                output.extend(failed)
                for event in failed:
                    projected = projected.apply(event)
                continue
            meal_state = replace(
                actor_state,
                location_id=actor_location_id,
                simulated_at=simulated_at,
            )
            meal_consequences = nourishment_events(
                cognitive_history,
                meal_state,
                simulated_at,
                projected,
                available_pence,
                pathos_busy=False,
                planned_schedule_id=entry.schedule_id,
                planned_meal_kind=meal_kind,
            )
            if not any(event.kind == "meal.eaten" for event in meal_consequences):
                unavailable = next(
                    (event for event in meal_consequences if event.kind == "meal.unavailable"),
                    None,
                )
                reason = (
                    str(unavailable.payload["reason"])
                    if unavailable is not None
                    else "By then, eating no longer answered a present bodily need."
                )
                if unavailable is not None:
                    output.append(unavailable)
                failed = _failed_open_plan_events(
                    projected,
                    entry,
                    intention.intention_id,
                    reason,
                    simulated_at,
                    causation_id=unavailable.event_id if unavailable is not None else None,
                )
                output.extend(failed)
                for event in failed:
                    projected = projected.apply(event)
                continue
        if action is ActionKind.REPAIR and entry.schedule_id.startswith("maintain-introduced-"):
            success_score = max(0.1, min(0.9, 0.25 + 0.65 * repair_mastery))
            sample = _sample(f"repair-attempt-{entry.schedule_id}")
            if sample >= success_score:
                correlation = entry.goal_id or entry.schedule_id
                attempted = DomainEvent(
                    "object.repair_attempted",
                    "pathos",
                    {
                        "object_id": entry.target_id or "unknown",
                        "schedule_id": entry.schedule_id,
                        "success_score": success_score,
                        "outcome_sample": sample,
                        "simulated_at": simulated_at.isoformat(),
                    },
                    correlation_id=correlation,
                )
                repair_failed = DomainEvent(
                    "object.repair_failed",
                    "pathos",
                    {
                        "object_id": entry.target_id or "unknown",
                        "schedule_id": entry.schedule_id,
                        "reason": "The attempted repair exceeded Pathos's present capability.",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=attempted.event_id,
                    correlation_id=correlation,
                )
                schedule_failed = DomainEvent(
                    "schedule.failed",
                    "pathos",
                    {
                        "schedule_id": entry.schedule_id,
                        "reason": "The physical repair attempt did not succeed.",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=repair_failed.event_id,
                    correlation_id=correlation,
                )
                abandoned_intention = DomainEvent(
                    "intention.abandoned",
                    "pathos",
                    {
                        "intention_id": intention.intention_id,
                        "reason": "The linked repair attempt failed.",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=repair_failed.event_id,
                    correlation_id=correlation,
                )
                consequences = [attempted, repair_failed, schedule_failed, abandoned_intention]
                for event in consequences:
                    projected = projected.apply(event)
                if entry.goal_id is not None:
                    abandoned_goal = DomainEvent(
                        "goal.abandoned",
                        "pathos",
                        {
                            "goal_id": entry.goal_id,
                            "reason": "The repair attempt failed and the object remains broken.",
                            "simulated_at": simulated_at.isoformat(),
                        },
                        causation_id=repair_failed.event_id,
                        correlation_id=correlation,
                    )
                    consequences.append(abandoned_goal)
                    projected = projected.apply(abandoned_goal)
                consequences.append(
                    DomainEvent(
                        "memory.recorded",
                        "pathos",
                        {
                            "text": f"My repair attempt failed: {entry.title}.",
                            "owner": "pathos",
                            "category": "setback",
                            "source": "deterministic-consequence",
                            "source_event_id": str(repair_failed.event_id),
                            "goal_id": entry.goal_id,
                            "object_id": entry.target_id,
                            "location_id": entry.location_id,
                            "importance": 0.76,
                            "confidence": 1.0,
                            "simulated_at": simulated_at.isoformat(),
                        },
                        causation_id=repair_failed.event_id,
                        correlation_id=correlation,
                    )
                )
                output.extend(consequences)
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
            goal_progress_delta=entry.goal_progress_delta or 0.5,
            execution_complete=bool(effort is not None and effort["ready"]),
        )
        output.extend(resolution.events)
        for event in resolution.events:
            projected = projected.apply(event)
        if not resolution.accepted:
            if entry.source_proposal_id is not None and entry.activity_type is not None:
                failed_events = _failed_open_plan_events(
                    projected,
                    entry,
                    intention.intention_id,
                    resolution.explanation,
                    simulated_at,
                )
                output.extend(failed_events)
                for event in failed_events:
                    projected = projected.apply(event)
            continue
        completion = next(
            event
            for event in resolution.events
            if event.kind
            == ("object.condition_changed" if action is ActionKind.REPAIR else "activity.completed")
        )
        output.extend(meal_consequences)
        for event in meal_consequences:
            projected = projected.apply(event)
        correlation = entry.commitment_id or entry.goal_id or entry.schedule_id

        if entry.activity_type is not None:
            output.append(
                DomainEvent(
                    "agency.activity_realized",
                    "pathos",
                    {
                        "schedule_id": entry.schedule_id,
                        "activity_type": entry.activity_type,
                        "action": action.value,
                        "title": entry.title,
                        "companion_id": entry.companion_id,
                        "location_id": entry.location_id,
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=completion.event_id,
                    correlation_id=entry.source_proposal_id or correlation,
                )
            )
        achieved = next(
            (event for event in resolution.events if event.kind == "goal.achieved"), None
        )
        if achieved is not None and entry.source_proposal_id is not None:
            output.append(
                DomainEvent(
                    "self_project.completed",
                    "pathos",
                    {
                        "proposal_id": entry.source_proposal_id,
                        "goal_id": entry.goal_id,
                        "title": projected.goals[entry.goal_id].title
                        if entry.goal_id
                        else entry.title,
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=achieved.event_id,
                    correlation_id=entry.source_proposal_id,
                )
            )

        def consequence(kind: str, payload: dict[str, object]) -> DomainEvent:
            return DomainEvent(
                kind,
                "pathos",
                payload,
                causation_id=completion.event_id,
                correlation_id=correlation,
            )

        if entry.resource_id is not None:
            output.append(
                consequence(
                    "object.used",
                    {
                        "object_id": entry.resource_id,
                        "schedule_id": entry.schedule_id,
                        "action": action.value,
                        "location_id": entry.location_id,
                        "simulated_at": simulated_at.isoformat(),
                    },
                )
            )

        if (
            action is ActionKind.REPAIR
            and entry.goal_id is not None
            and projected.goals[entry.goal_id].status == "active"
        ):
            progressed = consequence(
                "goal.progressed",
                {
                    "goal_id": entry.goal_id,
                    "progress_delta": 0.5,
                    "simulated_at": simulated_at.isoformat(),
                },
            )
            output.append(progressed)
            projected = projected.apply(progressed)

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
        if entry.companion_id is not None:
            output.extend(
                (
                    consequence(
                        "social.activity_completed",
                        {
                            "activity": entry.activity_type or action.value,
                            "person_id": entry.companion_id,
                            "schedule_id": entry.schedule_id,
                            "location_id": entry.location_id,
                            "simulated_at": simulated_at.isoformat(),
                        },
                    ),
                    consequence(
                        "relationship.changed",
                        {
                            "person_id": entry.companion_id,
                            "evidence_actor_id": "pathos",
                            "familiarity_delta": 0.03,
                            "trust_delta": 0.02,
                            "reason": "Pathos followed through on accepted shared activity.",
                            "simulated_at": simulated_at.isoformat(),
                        },
                    ),
                )
            )
        memory = consequence(
            "memory.recorded",
            {
                "text": f"I completed the planned {action.value}: {entry.title}.",
                "owner": "pathos",
                "category": "accomplishment",
                "source": "deterministic-consequence",
                "source_event_id": str(completion.event_id),
                "goal_id": entry.goal_id,
                "object_id": entry.target_id if action is ActionKind.REPAIR else entry.resource_id,
                "person_id": entry.companion_id,
                "location_id": entry.location_id,
                "importance": 0.7,
                "confidence": 1.0,
                "simulated_at": simulated_at.isoformat(),
            },
        )
        output.append(memory)
    return output


def prospective_memory_lapse(
    entry: CalendarEntry,
    intention_priority: float,
    history: Sequence[DomainEvent],
    *,
    cognitive_capacity: float = 1.0,
) -> bool:
    """Replay-stably miss only a low-stakes, self-chosen, one-off personal plan."""
    if not 0 <= intention_priority <= 1 or not 0 <= cognitive_capacity <= 1:
        raise ValueError("Prospective memory inputs must be between zero and one")
    if (
        entry.source_proposal_id is None
        or entry.activity_type is None
        or entry.activity_type == "plan_reconsideration"
        or entry.goal_id is not None
        or entry.commitment_id is not None
        or entry.companion_id is not None
        or intention_priority >= 0.6
    ):
        return False
    reminders = int(
        sum(
            event.kind == "mind.layer_pulsed"
            and event.payload.get("layer") == "prospective"
            and event.payload.get("focus_id") == entry.schedule_id
            for event in history
        )
    )
    strength = float(
        min(
            1.0,
            intention_priority + 0.12 * min(3, reminders) + 0.15 * cognitive_capacity,
        )
    )
    lapse_risk = max(0.03, 0.2 - 0.18 * strength)
    sample = int(sha256(f"prospective-lapse:{entry.schedule_id}".encode()).hexdigest()[:8], 16)
    return sample / 0xFFFFFFFF < lapse_risk


def _failed_open_plan_events(
    state: PlanningState,
    entry: CalendarEntry,
    intention_id: str,
    reason: str,
    simulated_at: datetime,
    causation_id: UUID | None = None,
) -> list[DomainEvent]:
    correlation = entry.source_proposal_id or entry.schedule_id
    project_step = entry.goal_id is not None and entry.source_proposal_id is not None
    missed = DomainEvent(
        "self_project.step_failed" if project_step else "agency.activity_missed",
        "pathos",
        {
            "schedule_id": entry.schedule_id,
            "activity_type": entry.activity_type,
            "companion_id": entry.companion_id,
            "proposal_id": entry.source_proposal_id,
            "goal_id": entry.goal_id,
            "reason": reason,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=causation_id,
        correlation_id=correlation,
    )
    events = [
        missed,
        DomainEvent(
            "schedule.failed",
            "pathos",
            {
                "schedule_id": entry.schedule_id,
                "reason": reason,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=missed.event_id,
            correlation_id=correlation,
        ),
        DomainEvent(
            "intention.abandoned",
            "pathos",
            {
                "intention_id": intention_id,
                "reason": reason,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=missed.event_id,
            correlation_id=correlation,
        ),
    ]
    if entry.goal_id is None or entry.source_proposal_id is None:
        return events
    project_failed = DomainEvent(
        "self_project.failed",
        "pathos",
        {
            "proposal_id": entry.source_proposal_id,
            "goal_id": entry.goal_id,
            "failed_schedule_id": entry.schedule_id,
            "reason": reason,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=missed.event_id,
        correlation_id=correlation,
    )
    events.append(project_failed)
    for other in state.calendar.values():
        if (
            other.goal_id == entry.goal_id
            and other.schedule_id != entry.schedule_id
            and other.status in {"scheduled", "interrupted"}
        ):
            events.append(
                DomainEvent(
                    "schedule.cancelled",
                    "pathos",
                    {
                        "schedule_id": other.schedule_id,
                        "reason": "Another required project step failed.",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=project_failed.event_id,
                    correlation_id=correlation,
                )
            )
    for other_intention in state.intentions.values():
        if (
            other_intention.goal_id == entry.goal_id
            and other_intention.intention_id != intention_id
            and other_intention.status == "active"
        ):
            events.append(
                DomainEvent(
                    "intention.abandoned",
                    "pathos",
                    {
                        "intention_id": other_intention.intention_id,
                        "reason": "Another required project step failed.",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=project_failed.event_id,
                    correlation_id=correlation,
                )
            )
    events.append(
        DomainEvent(
            "goal.abandoned",
            "pathos",
            {
                "goal_id": entry.goal_id,
                "reason": reason,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=project_failed.event_id,
            correlation_id=correlation,
        )
    )
    return events


def _sample(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
