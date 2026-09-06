"""Deterministic planning of explicitly accepted social requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Mapping

from eidos.domain.actions import ActionKind
from eidos.domain.events import DomainEvent
from eidos.domain.intentions import IntentionProposal, resolve_intention
from eidos.domain.planning import PlanningState
from eidos.domain.social import SocialRequest
from eidos.domain.travel import route_duration
from eidos.domain.world import location_allows_interval


@dataclass(frozen=True, slots=True)
class PlanResolution:
    accepted: bool
    code: str
    explanation: str
    events: tuple[DomainEvent, ...]


def plan_accepted_work(
    request: SocialRequest,
    *,
    state: PlanningState,
    actual_revision: int,
    simulated_at: datetime,
    preferred_start: datetime,
    opening_hours: Mapping[str, tuple[time, time]] | None = None,
    route_minutes: Mapping[frozenset[str], int] | None = None,
) -> PlanResolution:
    """Create a linked goal, commitment, schedule and intention as one candidate batch."""
    correlation = f"plan-{request.request_id}"

    def reject(code: str, explanation: str) -> PlanResolution:
        return PlanResolution(
            False,
            code,
            explanation,
            (
                DomainEvent(
                    "planning.rejected",
                    "pathos",
                    {
                        "request_id": request.request_id,
                        "code": code,
                        "explanation": explanation,
                        "simulated_at": simulated_at.isoformat(),
                    },
                    correlation_id=correlation,
                ),
            ),
        )

    if request.status != "accepted":
        return reject("request_not_accepted", "Planning cannot imply consent")
    responsible_actor = request.responder_id
    counterparty = request.requester_id
    if request.action == ActionKind.TALK.value and request.requester_id == "pathos":
        responsible_actor = "pathos"
        counterparty = request.responder_id
    if responsible_actor != "pathos":
        return reject("wrong_responsible_actor", "This planner only owns Pathos's commitments")
    try:
        action = ActionKind(request.action)
    except ValueError:
        return reject("unsupported_action", "No deterministic planner exists for this action yet")
    if action is ActionKind.REPAIR:
        item = state.objects.get(request.target_id)
        if item is None:
            return reject("unknown_target", "The requested object does not exist")
        if item.custodian_id != request.responder_id or item.location_id != request.location_id:
            return reject(
                "resource_unavailable", "The object is not available at the work location"
            )
    elif action not in {
        ActionKind.TALK,
        ActionKind.WORK,
        ActionKind.LEARN,
        ActionKind.ATTEND,
    }:
        return reject("unsupported_action", "No deterministic planner exists for this action yet")
    earliest = datetime.fromisoformat(request.earliest_start)
    due = datetime.fromisoformat(request.due_at)
    start = max(preferred_start, earliest, simulated_at)
    end = start + timedelta(hours=request.duration_hours)
    if end > due:
        return reject("deadline_infeasible", "The accepted deadline has no feasible work window")
    if not location_allows_interval(request.location_id, start, end, opening_hours):
        return reject("location_closed", "The activity falls outside the location's open hours")
    for entry in state.calendar.values():
        if entry.status != "scheduled" or entry.actor_id not in {None, responsible_actor}:
            continue
        other_start = datetime.fromisoformat(entry.starts_at)
        other_end = (
            datetime.fromisoformat(entry.ends_at)
            if entry.ends_at
            else other_start + timedelta(hours=1)
        )
        if start < other_end and other_start < end:
            return reject("schedule_conflict", f"The work overlaps {entry.title}")
        try:
            if other_end <= start:
                transition = route_duration(entry.location_id, request.location_id, route_minutes)
                transition_fits = other_end + transition <= start
            else:
                transition = route_duration(request.location_id, entry.location_id, route_minutes)
                transition_fits = end + transition <= other_start
        except ValueError:
            transition_fits = False
        if not transition_fits:
            return reject(
                "travel_conflict",
                f"There is not enough travel time between this work and {entry.title}",
            )
    goal_id = f"{request.request_id}-goal"
    commitment_id = f"{request.request_id}-commitment"
    schedule_id = f"{request.request_id}-schedule"
    intention_id = f"{request.request_id}-intention"
    common = {"request_id": request.request_id, "simulated_at": simulated_at.isoformat()}
    base = (
        DomainEvent(
            "goal.activated",
            "pathos",
            {**common, "goal_id": goal_id, "title": request.title},
            correlation_id=correlation,
        ),
        DomainEvent(
            "commitment.created",
            "pathos",
            {
                **common,
                "commitment_id": commitment_id,
                "title": f"{request.title} by the agreed deadline",
                "debtor_id": responsible_actor,
                "creditor_id": counterparty,
                "due_at": request.due_at,
                "goal_id": goal_id,
            },
            correlation_id=correlation,
        ),
        DomainEvent(
            "schedule.created",
            "pathos",
            {
                **common,
                "schedule_id": schedule_id,
                "title": request.title,
                "starts_at": start.isoformat(),
                "ends_at": end.isoformat(),
                "location_id": request.location_id,
                "actor_id": responsible_actor,
                "action": request.action,
                "target_id": request.target_id,
                "commitment_id": commitment_id,
                "goal_id": goal_id,
            },
            correlation_id=correlation,
        ),
    )
    projected = state
    for event in base:
        projected = projected.apply(event)
    intention = resolve_intention(
        IntentionProposal(
            proposal_id=f"intend-{request.request_id}",
            intention_id=intention_id,
            actor_id=responsible_actor,
            action=action,
            motivation=f"Honor the mutually accepted time with {counterparty}.",
            priority=0.9,
            expected_revision=actual_revision + len(base),
            goal_id=goal_id,
            target_id=request.target_id,
        ),
        state=projected,
        actual_revision=actual_revision + len(base),
        simulated_at=simulated_at,
    )
    if not intention.accepted:
        return reject("intention_rejected", "The accepted work could not form an intention")
    return PlanResolution(
        True,
        "accepted",
        "Accepted request has a feasible linked plan",
        (*base, *intention.events),
    )


def overdue_plan_events(state: PlanningState, simulated_at: datetime) -> list[DomainEvent]:
    """Resolve overdue obligations exactly once from projected nonterminal state."""
    events: list[DomainEvent] = []
    for commitment in state.commitments.values():
        if commitment.status != "active" or simulated_at <= datetime.fromisoformat(
            commitment.due_at
        ):
            continue
        missed = DomainEvent(
            "commitment.missed",
            "pathos",
            {
                "commitment_id": commitment.commitment_id,
                "reason": "The agreed deadline passed before completion.",
                "simulated_at": simulated_at.isoformat(),
            },
            correlation_id=commitment.request_id or commitment.commitment_id,
        )
        events.append(missed)

        def consequence(kind: str, payload: dict[str, object]) -> DomainEvent:
            return DomainEvent(
                kind,
                "pathos",
                payload,
                causation_id=missed.event_id,
                correlation_id=missed.correlation_id,
            )

        for entry in state.calendar.values():
            if entry.commitment_id == commitment.commitment_id and entry.status in {
                "scheduled",
                "interrupted",
            }:
                events.append(
                    consequence(
                        "schedule.failed",
                        {
                            "schedule_id": entry.schedule_id,
                            "reason": "The linked commitment deadline passed.",
                            "simulated_at": simulated_at.isoformat(),
                        },
                    )
                )
        if commitment.goal_id is not None:
            goal = state.goals.get(commitment.goal_id)
            if goal is not None and goal.status == "active":
                events.append(
                    consequence(
                        "goal.blocked",
                        {
                            "goal_id": goal.goal_id,
                            "reason": "The linked commitment was missed.",
                            "simulated_at": simulated_at.isoformat(),
                        },
                    )
                )
            for intention in state.intentions.values():
                if intention.goal_id == commitment.goal_id and intention.status == "active":
                    events.append(
                        consequence(
                            "intention.abandoned",
                            {
                                "intention_id": intention.intention_id,
                                "reason": "The intended deadline passed.",
                                "simulated_at": simulated_at.isoformat(),
                            },
                        )
                    )
        events.extend(
            (
                consequence(
                    "relationship.changed",
                    {
                        "person_id": commitment.creditor_id,
                        "evidence_actor_id": "pathos",
                        "trust_delta": -0.06,
                        "tension_delta": 0.05,
                        "reason": "Pathos missed an explicitly accepted commitment.",
                        "simulated_at": simulated_at.isoformat(),
                    },
                ),
                consequence(
                    "memory.recorded",
                    {
                        "text": f"I missed my commitment: {commitment.title}.",
                        "simulated_at": simulated_at.isoformat(),
                        "source": "deterministic-consequence",
                        "category": "commitment",
                        "person_id": commitment.creditor_id,
                        "goal_id": commitment.goal_id,
                        "owner": "pathos",
                        "importance": 0.9,
                        "confidence": 1.0,
                    },
                ),
            )
        )
    return events
