"""Resolve a completed reflective review through existing planning authority."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState
from eidos.domain.projects import GoalAbandonmentProposal, resolve_goal_abandonment
from eidos.domain.rescheduling import (
    ScheduleCancellationProposal,
    resolve_schedule_cancellation,
)


def reconsideration_decision_events(
    history: Sequence[DomainEvent],
    realized: DomainEvent,
    planning: PlanningState,
    actual_revision: int,
    simulated_at: datetime,
) -> list[DomainEvent]:
    """Make one typed decision after Pathos actually spends time reconsidering."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Reconsideration decision time must be timezone-aware")
    if (
        realized.kind != "agency.activity_realized"
        or realized.aggregate_id != "pathos"
        or realized.payload.get("activity_type") != "plan_reconsideration"
    ):
        return []
    schedule_id = realized.payload.get("schedule_id")
    if not isinstance(schedule_id, str):
        return []
    link = next(
        (
            event
            for event in reversed(history)
            if event.kind == "reflection.reconsideration_scheduled"
            and event.aggregate_id == "pathos"
            and event.payload.get("activity_schedule_id") == schedule_id
        ),
        None,
    )
    if link is None:
        return []
    decision_id = f"decision-{link.event_id}"
    if any(
        event.kind == "reflection.reconsideration_decided"
        and event.payload.get("decision_id") == decision_id
        for event in history
    ):
        return []
    target_type = str(link.payload["target_type"])
    target_id = str(link.payload["target_id"])
    decision, reason = _decision(target_type, target_id, planning)
    decided = DomainEvent(
        "reflection.reconsideration_decided",
        "pathos",
        {
            "decision_id": decision_id,
            "source_reconsideration_event_id": link.payload["source_reconsideration_event_id"],
            "review_schedule_id": schedule_id,
            "target_type": target_type,
            "target_id": target_id,
            "decision": decision,
            "text": reason,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=realized.event_id,
        correlation_id=link.correlation_id or decision_id,
    )
    output = [decided]
    if decision == "release_blocked_goal":
        goal_resolution = resolve_goal_abandonment(
            GoalAbandonmentProposal(
                proposal_id=f"release-{decision_id}",
                actor_id="pathos",
                goal_id=target_id,
                reason="After making time to reconsider, the blocked goal no longer fit.",
                expected_revision=actual_revision + 1,
            ),
            state=planning,
            actual_revision=actual_revision + 1,
            simulated_at=simulated_at,
        )
        output.extend(goal_resolution.events)
    elif decision == "release_optional_schedule":
        cancellation = resolve_schedule_cancellation(
            ScheduleCancellationProposal(
                proposal_id=f"release-{decision_id}",
                actor_id="pathos",
                schedule_id=target_id,
                reason="After reconsidering the interruption, the optional activity no longer fit.",
                expected_revision=actual_revision + 1,
            ),
            planning=planning,
            actual_revision=actual_revision + 1,
            simulated_at=simulated_at,
        )
        output.extend(cancellation.events)
    return output


def _decision(target_type: str, target_id: str, planning: PlanningState) -> tuple[str, str]:
    if target_type == "goal":
        goal = planning.goals.get(target_id)
        if goal is None or goal.status in {"achieved", "abandoned"}:
            return "acknowledge_closed", "The goal had already reached an ending."
        active_obligation = any(
            item.goal_id == target_id and item.status == "active"
            for item in planning.commitments.values()
        )
        if goal.status == "blocked" and not active_obligation:
            return "release_blocked_goal", "He decided to release the blocked personal goal."
        return "continue_goal", "He decided the goal still fit, even if its next step might change."
    if target_type == "schedule":
        entry = planning.calendar.get(target_id)
        if entry is None or entry.status in {"completed", "failed", "cancelled"}:
            return "acknowledge_closed", "The scheduled activity had already reached an ending."
        if entry.status == "interrupted":
            intention = (
                planning.intentions.get(entry.intention_id)
                if entry.intention_id is not None
                else None
            )
            if (
                entry.commitment_id is None
                and entry.goal_id is None
                and intention is not None
                and intention.status == "active"
                and intention.priority <= 0.35
            ):
                return (
                    "release_optional_schedule",
                    "He decided the interrupted optional activity was not important enough to reclaim.",
                )
            return "seek_new_time", "He decided the interrupted activity still needed a new time."
        return "keep_schedule", "He decided to leave the scheduled activity in place."
    if target_type == "commitment":
        commitment = planning.commitments.get(target_id)
        if commitment is None or commitment.status in {"fulfilled", "renegotiated"}:
            return "acknowledge_closed", "The commitment no longer needed a decision."
        if commitment.status == "missed":
            return "seek_repair", "He decided the missed commitment needed an honest follow-up."
        linked = [
            item
            for item in planning.calendar.values()
            if item.commitment_id == target_id and item.status in {"scheduled", "interrupted"}
        ]
        if any(item.status == "interrupted" for item in linked):
            return "consider_renegotiation", "He decided to ask for different terms or timing."
        return "keep_commitment", "He decided to keep the commitment as it stood."
    return "unsupported_target", "The old planning question no longer had a usable target."
