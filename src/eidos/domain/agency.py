"""Open-ended personal activity proposals with deterministic feasibility rules."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.actions import ActionKind
from eidos.domain.events import DomainEvent
from eidos.domain.intentions import IntentionProposal, resolve_intention
from eidos.domain.planning import PlanningState
from eidos.domain.proposals import ProposalRejected
from eidos.domain.travel import route_duration
from eidos.domain.world import location_allows_interval
from eidos.domain.world_catalog import WorldCatalog

AGENCY_ACTIONS = {ActionKind.WORK, ActionKind.LEARN, ActionKind.ATTEND}
_ACTIVITY_TYPE = re.compile(r"[a-z][a-z0-9_]{2,39}")
_FIELDS = {
    "activity_type",
    "title",
    "motivation",
    "action",
    "location_id",
    "resource_id",
    "companion_id",
    "starts_in_hours",
    "duration_hours",
    "priority",
}
_COMPLETION_CLAIMS = re.compile(
    r"\b(?:completed|finished|succeeded|achieved|already did|turned out)\b", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class AgencyCandidate:
    activity_type: str
    title: str
    motivation: str
    action: ActionKind
    location_id: str
    resource_id: str | None
    companion_id: str | None
    starts_in_hours: int
    duration_hours: int
    priority: float


@dataclass(frozen=True, slots=True)
class AgencyResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


def agency_output_schema(
    location_ids: list[str], resource_ids: list[str], companion_ids: list[str]
) -> dict[str, object]:
    """Return the strict transport schema; domain checks remain authoritative."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_FIELDS),
        "properties": {
            "activity_type": {"type": "string", "pattern": _ACTIVITY_TYPE.pattern},
            "title": {"type": "string", "minLength": 4, "maxLength": 100},
            "motivation": {"type": "string", "minLength": 8, "maxLength": 240},
            "action": {"type": "string", "enum": sorted(item.value for item in AGENCY_ACTIONS)},
            "location_id": {"type": "string", "enum": location_ids},
            "resource_id": {"type": "string", "enum": ["none", *resource_ids]},
            "companion_id": {"type": "string", "enum": ["none", *companion_ids]},
            "starts_in_hours": {"type": "integer", "minimum": 4, "maximum": 72},
            "duration_hours": {"type": "integer", "minimum": 1, "maximum": 4},
            "priority": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def parse_agency_candidate(content: str) -> AgencyCandidate:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Agency proposal was not valid JSON") from None
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ProposalRejected("invalid_shape", "Agency proposal fields did not match schema v1")
    for field, minimum, maximum in (("title", 4, 100), ("motivation", 8, 240)):
        item = value[field]
        if not isinstance(item, str) or not minimum <= len(item.strip()) <= maximum:
            raise ProposalRejected("invalid_text", f"{field} length is outside policy")
    activity_type = value["activity_type"]
    if not isinstance(activity_type, str) or not _ACTIVITY_TYPE.fullmatch(activity_type):
        raise ProposalRejected(
            "invalid_activity_type", "activity_type must be a stable open-vocabulary slug"
        )
    for field in ("location_id", "resource_id", "companion_id"):
        if not isinstance(value[field], str) or not value[field]:
            raise ProposalRejected("invalid_identifier", f"{field} must be a non-empty string")
    try:
        action = ActionKind(value["action"])
    except (TypeError, ValueError):
        raise ProposalRejected("unknown_action", "Agency action is not supported") from None
    if action not in AGENCY_ACTIONS:
        raise ProposalRejected("unknown_action", "Agency action is not safely schedulable")
    starts = value["starts_in_hours"]
    duration = value["duration_hours"]
    priority = value["priority"]
    if isinstance(starts, bool) or not isinstance(starts, int) or not 4 <= starts <= 72:
        raise ProposalRejected("invalid_start", "starts_in_hours must be an integer from 4 to 72")
    if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 4:
        raise ProposalRejected("invalid_duration", "duration_hours must be an integer from 1 to 4")
    if (
        isinstance(priority, bool)
        or not isinstance(priority, (int, float))
        or not 0 <= priority <= 1
    ):
        raise ProposalRejected("invalid_priority", "priority must be between zero and one")
    if _COMPLETION_CLAIMS.search(value["title"]) or _COMPLETION_CLAIMS.search(value["motivation"]):
        raise ProposalRejected(
            "claims_outcome", "A proposal cannot claim an activity already succeeded"
        )
    return AgencyCandidate(
        activity_type,
        value["title"].strip(),
        value["motivation"].strip(),
        action,
        value["location_id"],
        None if value["resource_id"] == "none" else value["resource_id"],
        None if value["companion_id"] == "none" else value["companion_id"],
        starts,
        duration,
        float(priority),
    )


def resolve_agency_candidate(
    candidate: AgencyCandidate,
    *,
    proposal_id: str,
    state: PlanningState,
    catalog: WorldCatalog,
    known_companion_ids: set[str],
    actual_revision: int,
    simulated_at: datetime,
    recent_activity_signatures: Sequence[tuple[str, str, str]] = (),
) -> AgencyResolution:
    """Admit a novel idea only when it can become a physically coherent plan."""
    common = {
        "proposal_id": proposal_id,
        "activity_type": candidate.activity_type,
        "title": candidate.title,
        "motivation": candidate.motivation,
        "action": candidate.action.value,
        "location_id": candidate.location_id,
        "resource_id": candidate.resource_id,
        "companion_id": candidate.companion_id,
        "simulated_at": simulated_at.isoformat(),
    }
    proposed = DomainEvent("agency.activity_proposed", "pathos", common, correlation_id=proposal_id)

    def reject(code: str, explanation: str) -> AgencyResolution:
        return AgencyResolution(
            False,
            code,
            (
                proposed,
                DomainEvent(
                    "agency.activity_rejected",
                    "pathos",
                    {**common, "code": code, "explanation": explanation},
                    causation_id=proposed.event_id,
                    correlation_id=proposal_id,
                ),
            ),
        )

    if simulated_at.utcoffset() is None:
        return reject("naive_time", "Agency planning needs timezone-aware time")
    if candidate.location_id not in catalog.places:
        return reject("unknown_location", "The proposed place does not exist")
    if candidate.companion_id is not None and candidate.companion_id not in known_companion_ids:
        return reject("unknown_companion", "The proposed companion is not known")
    candidate_signature = (
        candidate.activity_type,
        candidate.location_id,
        candidate.companion_id or "solo",
    )
    exact_repetitions = sum(
        signature == candidate_signature for signature in recent_activity_signatures
    )
    activity_repetitions = sum(
        signature[0] == candidate.activity_type for signature in recent_activity_signatures
    )
    if exact_repetitions >= 6 or activity_repetitions >= 8:
        return reject(
            "overused_pattern",
            "This recent activity pattern needs time or meaningful variation before repeating.",
        )
    resource = state.objects.get(candidate.resource_id) if candidate.resource_id else None
    if candidate.resource_id is not None and resource is None:
        return reject("unknown_resource", "The proposed resource does not exist")
    if resource is not None:
        shared = resource.owner_id == resource.custodian_id == "community"
        if resource.custodian_id != "pathos" and not shared:
            return reject("resource_unavailable", "Pathos cannot plan with an object he cannot use")
        if (
            resource.location_id != candidate.location_id
            or resource.condition not in {"good", "usable", "repaired"}
            or resource.quantity == 0
        ):
            return reject(
                "resource_unavailable", "The object will not be usable at the proposed place"
            )
    starts_at = simulated_at + timedelta(hours=candidate.starts_in_hours)
    ends_at = starts_at + timedelta(hours=candidate.duration_hours)
    if not location_allows_interval(
        candidate.location_id, starts_at, ends_at, catalog.opening_hours
    ):
        return reject("place_closed", "The place is not open for the whole activity")
    for entry in state.calendar.values():
        if entry.status != "scheduled" or entry.actor_id not in {None, "pathos"}:
            continue
        other_start = datetime.fromisoformat(entry.starts_at)
        other_end = datetime.fromisoformat(entry.ends_at) if entry.ends_at else other_start
        if starts_at < other_end and other_start < ends_at:
            return reject("schedule_conflict", f"The activity overlaps {entry.title}")
        try:
            if other_end <= starts_at:
                fits = (
                    other_end
                    + route_duration(
                        entry.location_id, candidate.location_id, catalog.route_minutes
                    )
                    <= starts_at
                )
            else:
                fits = (
                    ends_at
                    + route_duration(
                        candidate.location_id, entry.location_id, catalog.route_minutes
                    )
                    <= other_start
                )
        except ValueError:
            fits = False
        if not fits:
            return reject("travel_conflict", f"Travel time conflicts with {entry.title}")
    schedule_id = f"{proposal_id}-schedule"
    intention_id = f"{proposal_id}-intention"
    target_id = candidate.companion_id or candidate.location_id
    accepted = DomainEvent(
        "agency.activity_accepted",
        "pathos",
        {**common, "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()},
        causation_id=proposed.event_id,
        correlation_id=proposal_id,
    )
    schedule = DomainEvent(
        "schedule.created",
        "pathos",
        {
            "schedule_id": schedule_id,
            "title": candidate.title,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "location_id": candidate.location_id,
            "actor_id": "pathos",
            "action": candidate.action.value,
            "target_id": target_id,
            "resource_id": candidate.resource_id,
            "companion_id": candidate.companion_id,
            "activity_type": candidate.activity_type,
            "source_proposal_id": proposal_id,
            "intention_id": intention_id,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=accepted.event_id,
        correlation_id=proposal_id,
    )
    projected = state.apply(schedule)
    intention = resolve_intention(
        IntentionProposal(
            proposal_id=f"intend-{proposal_id}",
            intention_id=intention_id,
            actor_id="pathos",
            action=candidate.action,
            motivation=candidate.motivation,
            priority=candidate.priority,
            expected_revision=actual_revision + 3,
            target_id=target_id,
        ),
        state=projected,
        actual_revision=actual_revision + 3,
        simulated_at=simulated_at,
    )
    if not intention.accepted:
        return reject("intention_rejected", "The feasible activity could not form an intention")
    return AgencyResolution(True, "accepted", (proposed, accepted, schedule, *intention.events))
