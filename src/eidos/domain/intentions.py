"""Versioned intention proposals resolved against owned goals and world state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from eidos.domain.actions import ActionKind
from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState
from eidos.domain.proposals import ProposalRejected


@dataclass(frozen=True, slots=True)
class IntentionProposal:
    proposal_id: str
    intention_id: str
    actor_id: str
    action: ActionKind
    motivation: str
    priority: float
    expected_revision: int
    goal_id: str | None = None
    target_id: str | None = None
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class IntentionResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


_FIELDS = {
    "schema_version",
    "proposal_id",
    "intention_id",
    "actor_id",
    "action",
    "motivation",
    "priority",
    "expected_revision",
    "goal_id",
    "target_id",
}


def parse_intention_proposal(content: str) -> IntentionProposal:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Intention proposal was not valid JSON") from None
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ProposalRejected("invalid_shape", "Intention proposal fields did not match schema v1")
    if value["schema_version"] != 1:
        raise ProposalRejected("unsupported_schema", "Intention proposal schema is not supported")
    for field in ("proposal_id", "intention_id", "actor_id", "motivation"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ProposalRejected("invalid_text", f"{field} must be a non-empty string")
    for field in ("goal_id", "target_id"):
        if value[field] is not None and (
            not isinstance(value[field], str) or not value[field].strip()
        ):
            raise ProposalRejected("invalid_identifier", f"{field} must be null or non-empty")
    priority = value["priority"]
    if (
        isinstance(priority, bool)
        or not isinstance(priority, (int, float))
        or not 0 <= priority <= 1
    ):
        raise ProposalRejected("invalid_priority", "priority must be between zero and one")
    revision = value["expected_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ProposalRejected("invalid_revision", "expected_revision must be non-negative")
    try:
        action = ActionKind(value["action"])
    except (TypeError, ValueError):
        raise ProposalRejected("unknown_action", "Intended action is not supported") from None
    return IntentionProposal(
        proposal_id=value["proposal_id"],
        intention_id=value["intention_id"],
        actor_id=value["actor_id"],
        action=action,
        motivation=value["motivation"],
        priority=float(priority),
        expected_revision=revision,
        goal_id=value["goal_id"],
        target_id=value["target_id"],
    )


def resolve_intention(
    proposal: IntentionProposal,
    *,
    state: PlanningState,
    actual_revision: int,
    simulated_at: datetime,
) -> IntentionResolution:
    common = {
        "proposal_id": proposal.proposal_id,
        "intention_id": proposal.intention_id,
        "actor_id": proposal.actor_id,
        "action": proposal.action.value,
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at.isoformat(),
    }
    proposed = DomainEvent(
        "intention.proposed", proposal.actor_id, common, correlation_id=proposal.proposal_id
    )

    def outcome(kind: str, extra: Mapping[str, Any]) -> DomainEvent:
        return DomainEvent(
            kind,
            proposal.actor_id,
            {**common, **extra},
            causation_id=proposed.event_id,
            correlation_id=proposal.proposal_id,
        )

    def reject(code: str, explanation: str) -> IntentionResolution:
        return IntentionResolution(
            False,
            code,
            (proposed, outcome("intention.rejected", {"code": code, "explanation": explanation})),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The world changed after the intention was proposed")
    if proposal.intention_id in state.intentions:
        return reject("duplicate_intention", "That intention already exists")
    if proposal.goal_id is not None:
        goal = state.goals.get(proposal.goal_id)
        if goal is None:
            return reject("unknown_goal", "The intention refers to an unknown goal")
        if goal.status != "active":
            return reject("inactive_goal", "The intention's goal is not active")
    if proposal.action is ActionKind.REPAIR:
        if proposal.target_id is None or proposal.target_id not in state.objects:
            return reject("unknown_target", "A repair intention needs an existing object")
    adopted = outcome(
        "intention.adopted",
        {
            "motivation": proposal.motivation,
            "priority": proposal.priority,
            "goal_id": proposal.goal_id,
            "target_id": proposal.target_id,
        },
    )
    return IntentionResolution(True, "accepted", (proposed, adopted))
