"""Typed, audited decisions about an actor's unfinished personal goals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState
from eidos.domain.proposals import ProposalRejected


@dataclass(frozen=True, slots=True)
class GoalAbandonmentProposal:
    proposal_id: str
    actor_id: str
    goal_id: str
    reason: str
    expected_revision: int
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class GoalAbandonmentResolution:
    accepted: bool
    code: str
    explanation: str
    events: tuple[DomainEvent, ...]


_FIELDS = {
    "schema_version",
    "proposal_id",
    "actor_id",
    "goal_id",
    "reason",
    "expected_revision",
}


def parse_goal_abandonment_proposal(content: str) -> GoalAbandonmentProposal:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Goal decision was not valid JSON") from None
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ProposalRejected("invalid_shape", "Goal decision fields did not match schema v1")
    if value["schema_version"] != 1:
        raise ProposalRejected("unsupported_schema", "Goal decision schema is not supported")
    for field in ("proposal_id", "actor_id", "goal_id", "reason"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ProposalRejected("invalid_text", f"{field} must be a non-empty string")
    revision = value["expected_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ProposalRejected("invalid_revision", "expected_revision must be non-negative")
    return GoalAbandonmentProposal(
        proposal_id=value["proposal_id"],
        actor_id=value["actor_id"],
        goal_id=value["goal_id"],
        reason=value["reason"],
        expected_revision=revision,
    )


def resolve_goal_abandonment(
    proposal: GoalAbandonmentProposal,
    *,
    state: PlanningState,
    actual_revision: int,
    simulated_at: datetime,
) -> GoalAbandonmentResolution:
    common: dict[str, Any] = {
        "proposal_id": proposal.proposal_id,
        "goal_id": proposal.goal_id,
        "reason": proposal.reason,
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at.isoformat(),
    }
    proposed = DomainEvent(
        "goal.abandonment_proposed",
        proposal.actor_id,
        common,
        correlation_id=proposal.proposal_id,
    )

    def outcome(kind: str, extra: Mapping[str, Any]) -> DomainEvent:
        return DomainEvent(
            kind,
            proposal.actor_id,
            {**common, **extra},
            causation_id=proposed.event_id,
            correlation_id=proposal.proposal_id,
        )

    def reject(code: str, explanation: str) -> GoalAbandonmentResolution:
        rejected = outcome("goal.abandonment_rejected", {"code": code, "explanation": explanation})
        return GoalAbandonmentResolution(False, code, explanation, (proposed, rejected))

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The world changed after this decision was proposed")
    if proposal.actor_id != "pathos":
        return reject("wrong_actor", "This goal planner only controls Pathos's own goals")
    goal = state.goals.get(proposal.goal_id)
    if goal is None:
        return reject("unknown_goal", "The goal does not exist")
    if goal.status not in {"active", "blocked"}:
        return reject("finished_goal", "The goal is already finished")
    if any(
        item.goal_id == goal.goal_id and item.status == "active"
        for item in state.commitments.values()
    ):
        return reject(
            "active_commitment",
            "An obligation to another person must be fulfilled, missed, or renegotiated first",
        )

    accepted = outcome("goal.abandonment_accepted", {})

    def effect(kind: str, payload: Mapping[str, Any]) -> DomainEvent:
        return DomainEvent(
            kind,
            proposal.actor_id,
            payload,
            causation_id=accepted.event_id,
            correlation_id=proposal.proposal_id,
        )

    effects: list[DomainEvent] = []
    for entry in state.calendar.values():
        if entry.goal_id == goal.goal_id and entry.status in {"scheduled", "interrupted"}:
            effects.append(
                effect(
                    "schedule.cancelled",
                    {
                        "schedule_id": entry.schedule_id,
                        "reason": proposal.reason,
                        "simulated_at": simulated_at.isoformat(),
                    },
                )
            )
    for intention in state.intentions.values():
        if intention.goal_id == goal.goal_id and intention.status == "active":
            effects.append(
                effect(
                    "intention.abandoned",
                    {
                        "intention_id": intention.intention_id,
                        "reason": proposal.reason,
                        "simulated_at": simulated_at.isoformat(),
                    },
                )
            )
    effects.append(
        effect(
            "goal.abandoned",
            {
                "goal_id": goal.goal_id,
                "reason": proposal.reason,
                "simulated_at": simulated_at.isoformat(),
            },
        )
    )
    return GoalAbandonmentResolution(
        True,
        "accepted",
        "The personal goal and its unfinished work were closed",
        (proposed, accepted, *effects),
    )
