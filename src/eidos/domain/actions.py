"""Typed action proposals and deterministic world-side resolution.

Language models may suggest actions, but only this module can translate a
proposal into accepted domain events. Rejections are durable facts too, which
makes bad or stale proposals inspectable instead of silently disappearing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping
from uuid import UUID

from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState
from eidos.domain.proposals import ProposalRejected


class ActionKind(StrEnum):
    MOVE = "move"
    REPAIR = "repair"
    REST = "rest"
    TALK = "talk"
    WORK = "work"
    LEARN = "learn"
    ATTEND = "attend"


@dataclass(frozen=True, slots=True)
class ActionProposal:
    proposal_id: str
    actor_id: str
    action: ActionKind
    expected_revision: int
    target_id: str | None = None
    location_id: str | None = None
    schedule_id: str | None = None
    intention_id: str | None = None
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class ActionResolution:
    accepted: bool
    code: str
    explanation: str
    events: tuple[DomainEvent, ...]


_ACTION_FIELDS = {
    "schema_version",
    "proposal_id",
    "actor_id",
    "action",
    "expected_revision",
    "target_id",
    "location_id",
    "schedule_id",
    "intention_id",
}


def parse_action_proposal(content: str) -> ActionProposal:
    """Parse the exact versioned JSON contract used at the model boundary."""

    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Action proposal was not valid JSON") from None
    if not isinstance(value, dict) or set(value) != _ACTION_FIELDS:
        raise ProposalRejected("invalid_shape", "Action proposal fields did not match schema v1")
    if value["schema_version"] != 1:
        raise ProposalRejected("unsupported_schema", "Action proposal schema is not supported")
    for key in ("proposal_id", "actor_id"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ProposalRejected("invalid_identifier", f"{key} must be a non-empty string")
    for key in ("target_id", "location_id", "schedule_id", "intention_id"):
        if value[key] is not None and (not isinstance(value[key], str) or not value[key].strip()):
            raise ProposalRejected("invalid_identifier", f"{key} must be null or non-empty")
    revision = value["expected_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ProposalRejected(
            "invalid_revision", "expected_revision must be a non-negative integer"
        )
    try:
        action = ActionKind(value["action"])
    except (TypeError, ValueError):
        raise ProposalRejected(
            "unknown_action", "Action is outside the supported vocabulary"
        ) from None
    return ActionProposal(
        proposal_id=value["proposal_id"],
        actor_id=value["actor_id"],
        action=action,
        expected_revision=revision,
        target_id=value["target_id"],
        location_id=value["location_id"],
        schedule_id=value["schedule_id"],
        intention_id=value["intention_id"],
    )


def resolve_action(
    proposal: ActionProposal,
    *,
    state: PlanningState,
    actor_location_id: str,
    actual_revision: int,
    simulated_at: datetime,
) -> ActionResolution:
    """Validate a proposal against current state and return its only legal effects."""

    common: dict[str, Any] = {
        "proposal_id": proposal.proposal_id,
        "action": proposal.action.value,
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at.isoformat(),
    }
    proposed = DomainEvent(
        "action.proposed", proposal.actor_id, common, correlation_id=proposal.proposal_id
    )

    def effect(
        kind: str, payload: Mapping[str, Any], causation_id: UUID = proposed.event_id
    ) -> DomainEvent:
        return DomainEvent(
            kind,
            proposal.actor_id,
            payload,
            causation_id=causation_id,
            correlation_id=proposal.proposal_id,
        )

    def reject(code: str, explanation: str) -> ActionResolution:
        rejected = effect("action.rejected", {**common, "code": code, "explanation": explanation})
        return ActionResolution(False, code, explanation, (proposed, rejected))

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The world changed after this action was proposed")
    if proposal.intention_id is not None:
        intention = state.intentions.get(proposal.intention_id)
        if intention is None:
            return reject("unknown_intention", "The action refers to an unknown intention")
        if intention.status != "active":
            return reject("inactive_intention", "The action's intention is not active")
        if intention.actor_id != proposal.actor_id or intention.action != proposal.action.value:
            return reject("intention_mismatch", "The action does not match its owned intention")
        if intention.target_id is not None and intention.target_id != proposal.target_id:
            return reject("intention_mismatch", "The action target does not match its intention")
        if intention.goal_id is not None:
            goal = state.goals.get(intention.goal_id)
            if goal is None:
                return reject("unknown_goal", "The action's intention refers to an unknown goal")
            if goal.status != "active":
                return reject("inactive_goal", "The action's intention belongs to an inactive goal")

    effects: list[DomainEvent] = []
    intention = (
        state.intentions.get(proposal.intention_id) if proposal.intention_id is not None else None
    )
    if proposal.action is ActionKind.REPAIR:
        missing = _missing(proposal, "target_id", "schedule_id")
        if missing:
            return reject("missing_argument", f"Repair requires {missing}")
        assert proposal.target_id is not None and proposal.schedule_id is not None
        item = state.objects.get(proposal.target_id)
        if item is None:
            return reject("unknown_target", "The object does not exist")
        schedule = state.calendar.get(proposal.schedule_id)
        if schedule is None:
            return reject("unknown_schedule", "The scheduled work does not exist")
        if item.custodian_id != proposal.actor_id:
            return reject("no_custody", "The actor does not have custody of the object")
        if item.location_id != actor_location_id or schedule.location_id != actor_location_id:
            return reject(
                "wrong_location", "The actor, object, and scheduled work must be co-located"
            )
        if item.condition != "broken":
            return reject("invalid_condition", "Only a broken object can be repaired")
        if schedule.status != "scheduled":
            return reject("inactive_schedule", "The work is not currently scheduled")
        try:
            starts_at = datetime.fromisoformat(schedule.starts_at)
        except ValueError:
            return reject("invalid_schedule_time", "The scheduled start time is invalid")
        if simulated_at < starts_at:
            return reject("too_early", "The scheduled work has not started")
        if schedule.ends_at is not None:
            try:
                ends_at = datetime.fromisoformat(schedule.ends_at)
            except ValueError:
                return reject("invalid_schedule_time", "The scheduled end time is invalid")
            if simulated_at < ends_at:
                return reject("work_incomplete", "The scheduled work duration has not elapsed")
        effects.extend(
            (
                effect(
                    "object.condition_changed",
                    {
                        "object_id": item.object_id,
                        "condition": "repaired",
                        "simulated_at": simulated_at,
                    },
                ),
                effect(
                    "schedule.completed",
                    {"schedule_id": schedule.schedule_id, "simulated_at": simulated_at},
                ),
            )
        )
    elif proposal.action is ActionKind.MOVE:
        if proposal.location_id is None:
            return reject("missing_argument", "Move requires location_id")
        if proposal.location_id == actor_location_id:
            return reject("already_there", "The actor is already at that location")
        effects.append(
            effect(
                "pathos.moved",
                {"location_id": proposal.location_id, "simulated_at": simulated_at},
            )
        )
    elif proposal.action is ActionKind.REST:
        effects.append(
            effect(
                "action.rested",
                {"location_id": actor_location_id, "simulated_at": simulated_at},
            )
        )
    elif proposal.action is ActionKind.TALK:
        if proposal.target_id is None:
            return reject("missing_argument", "Talk requires target_id")
        if proposal.intention_id is not None and proposal.schedule_id is None:
            return reject("missing_argument", "A planned conversation requires schedule_id")
        if proposal.schedule_id is not None:
            schedule = state.calendar.get(proposal.schedule_id)
            if schedule is None:
                return reject("unknown_schedule", "The scheduled conversation does not exist")
            if schedule.status != "scheduled":
                return reject("inactive_schedule", "The conversation is not currently scheduled")
            if schedule.location_id != actor_location_id:
                return reject("wrong_location", "The actor must be at the meeting place")
            if simulated_at < datetime.fromisoformat(schedule.starts_at):
                return reject("too_early", "The scheduled conversation has not started")
            effects.append(
                effect(
                    "schedule.completed",
                    {"schedule_id": schedule.schedule_id, "simulated_at": simulated_at},
                )
            )
        effects.append(
            effect(
                "conversation.requested",
                {"person_id": proposal.target_id, "simulated_at": simulated_at},
            )
        )
    elif proposal.action in {ActionKind.WORK, ActionKind.LEARN, ActionKind.ATTEND}:
        if proposal.schedule_id is None:
            return reject(
                "missing_argument", f"{proposal.action.value.title()} requires schedule_id"
            )
        schedule = state.calendar.get(proposal.schedule_id)
        if schedule is None:
            return reject("unknown_schedule", "The scheduled activity does not exist")
        if schedule.status != "scheduled":
            return reject("inactive_schedule", "The activity is not currently scheduled")
        if schedule.actor_id not in {None, proposal.actor_id}:
            return reject("wrong_actor", "The schedule belongs to another actor")
        if schedule.action not in {None, proposal.action.value}:
            return reject("schedule_mismatch", "The action does not match the schedule")
        if schedule.target_id is not None and schedule.target_id != proposal.target_id:
            return reject("schedule_mismatch", "The target does not match the schedule")
        if schedule.location_id != actor_location_id:
            return reject("wrong_location", "The actor must be at the activity location")
        if schedule.resource_id is not None:
            resource = state.objects.get(schedule.resource_id)
            if resource is None:
                return reject("missing_resource", "The scheduled resource does not exist")
            shared_at_site = (
                proposal.action is ActionKind.ATTEND
                and resource.owner_id == "community"
                and resource.custodian_id == "community"
            )
            if resource.custodian_id != proposal.actor_id and not shared_at_site:
                return reject("resource_unavailable", "The actor does not hold the resource")
            if resource.location_id != actor_location_id or resource.condition not in {
                "good",
                "usable",
                "repaired",
            }:
                return reject("resource_unavailable", "The resource is not usable at this place")
        starts_at = datetime.fromisoformat(schedule.starts_at)
        ends_at = datetime.fromisoformat(schedule.ends_at) if schedule.ends_at else starts_at
        if simulated_at < starts_at:
            return reject("too_early", "The scheduled activity has not started")
        if proposal.action in {ActionKind.WORK, ActionKind.LEARN} and simulated_at < ends_at:
            return reject("activity_incomplete", "The scheduled activity duration has not elapsed")
        if proposal.action is ActionKind.ATTEND and simulated_at > ends_at:
            return reject("activity_missed", "The attendance window has passed")
        schedule_completed = effect(
            "schedule.completed",
            {"schedule_id": schedule.schedule_id, "simulated_at": simulated_at},
        )
        activity_completed = effect(
            "activity.completed",
            {
                "activity": proposal.action.value,
                "schedule_id": schedule.schedule_id,
                "target_id": proposal.target_id,
                "location_id": actor_location_id,
                "simulated_at": simulated_at,
            },
        )
        effects.extend((schedule_completed, activity_completed))
        if intention is not None and intention.goal_id is not None:
            goal = state.goals[intention.goal_id]
            progressed = effect(
                "goal.progressed",
                {
                    "goal_id": goal.goal_id,
                    "progress_delta": 0.5,
                    "simulated_at": simulated_at,
                },
                activity_completed.event_id,
            )
            effects.append(progressed)
            if goal.progress + 0.5 >= 1:
                effects.append(
                    effect(
                        "goal.achieved",
                        {"goal_id": goal.goal_id, "simulated_at": simulated_at},
                        progressed.event_id,
                    )
                )

    accepted = effect("action.accepted", common)
    if proposal.intention_id is not None:
        effects.append(
            effect(
                "intention.completed",
                {"intention_id": proposal.intention_id, "simulated_at": simulated_at},
            )
        )
    return ActionResolution(
        True, "accepted", "Action passed deterministic rules", (proposed, accepted, *effects)
    )


def _missing(proposal: ActionProposal, *fields: str) -> str | None:
    values: Mapping[str, str | None] = {
        "target_id": proposal.target_id,
        "location_id": proposal.location_id,
        "schedule_id": proposal.schedule_id,
        "intention_id": proposal.intention_id,
    }
    return next((field for field in fields if values[field] is None), None)
