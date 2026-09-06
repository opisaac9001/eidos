"""Open-ended multi-step projects admitted through deterministic planning rules."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from eidos.domain.actions import ActionKind
from eidos.domain.events import DomainEvent
from eidos.domain.intentions import IntentionProposal, resolve_intention
from eidos.domain.planning import CalendarEntry, PlanningState
from eidos.domain.proposals import ProposalRejected
from eidos.domain.travel import route_duration
from eidos.domain.world import location_allows_interval
from eidos.domain.world_catalog import WorldCatalog

_SLUG = re.compile(r"[a-z][a-z0-9_]{2,39}")
_OUTCOME = re.compile(r"\b(?:completed|finished|succeeded|achieved|already did)\b", re.I)
_PROJECT_FIELDS = {"project_type", "title", "motivation", "priority", "steps"}
_STEP_FIELDS = {
    "activity_type",
    "title",
    "action",
    "location_id",
    "resource_id",
    "day_offset",
    "scheduled_hour",
    "duration_hours",
}
_ACTIONS = {ActionKind.WORK, ActionKind.LEARN, ActionKind.ATTEND}


@dataclass(frozen=True, slots=True)
class ProjectStep:
    activity_type: str
    title: str
    action: ActionKind
    location_id: str
    resource_id: str | None
    day_offset: int
    scheduled_hour: int
    duration_hours: int


@dataclass(frozen=True, slots=True)
class SelfProjectCandidate:
    project_type: str
    title: str
    motivation: str
    priority: float
    steps: tuple[ProjectStep, ...]


@dataclass(frozen=True, slots=True)
class SelfProjectResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


def self_project_output_schema(
    location_ids: list[str], resource_ids: list[str]
) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_PROJECT_FIELDS),
        "properties": {
            "project_type": {"type": "string", "pattern": _SLUG.pattern},
            "title": {"type": "string", "minLength": 5, "maxLength": 100},
            "motivation": {"type": "string", "minLength": 8, "maxLength": 240},
            "priority": {"type": "number", "minimum": 0, "maximum": 1},
            "steps": {
                "type": "array",
                "minItems": 2,
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": sorted(_STEP_FIELDS),
                    "properties": {
                        "activity_type": {"type": "string", "pattern": _SLUG.pattern},
                        "title": {"type": "string", "minLength": 4, "maxLength": 100},
                        "action": {
                            "type": "string",
                            "enum": sorted(item.value for item in _ACTIONS),
                        },
                        "location_id": {"type": "string", "enum": location_ids},
                        "resource_id": {
                            "type": "string",
                            "enum": ["none", *resource_ids],
                        },
                        "day_offset": {"type": "integer", "minimum": 1, "maximum": 14},
                        "scheduled_hour": {"type": "integer", "minimum": 6, "maximum": 20},
                        "duration_hours": {"type": "integer", "minimum": 1, "maximum": 3},
                    },
                },
            },
        },
    }


def parse_self_project_candidate(content: str) -> SelfProjectCandidate:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Project proposal was not valid JSON") from None
    if not isinstance(value, dict) or set(value) != _PROJECT_FIELDS:
        raise ProposalRejected("invalid_shape", "Project proposal fields did not match schema v1")
    project_type = _slug(value["project_type"], "project_type")
    title = _text(value["title"], "title", 5, 100)
    motivation = _text(value["motivation"], "motivation", 8, 240)
    priority = value["priority"]
    if (
        isinstance(priority, bool)
        or not isinstance(priority, (int, float))
        or not 0 <= priority <= 1
    ):
        raise ProposalRejected("invalid_priority", "priority must be between zero and one")
    raw_steps = value["steps"]
    if not isinstance(raw_steps, list) or not 2 <= len(raw_steps) <= 4:
        raise ProposalRejected("invalid_steps", "A project needs two to four steps")
    steps: list[ProjectStep] = []
    for raw in raw_steps:
        if not isinstance(raw, dict) or set(raw) != _STEP_FIELDS:
            raise ProposalRejected(
                "invalid_step_shape", "Project step fields did not match schema v1"
            )
        try:
            action = ActionKind(raw["action"])
        except (TypeError, ValueError):
            raise ProposalRejected("unknown_action", "Project step action is unsupported") from None
        if action not in _ACTIONS:
            raise ProposalRejected(
                "unknown_action", "Project step action is not safely schedulable"
            )
        day, hour, duration = raw["day_offset"], raw["scheduled_hour"], raw["duration_hours"]
        if isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= 14:
            raise ProposalRejected("invalid_day", "Project step day must be from one to fourteen")
        if isinstance(hour, bool) or not isinstance(hour, int) or not 6 <= hour <= 20:
            raise ProposalRejected("invalid_hour", "Project step hour must be from six to twenty")
        if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 3:
            raise ProposalRejected(
                "invalid_duration", "Project step duration must be one to three hours"
            )
        location, resource = raw["location_id"], raw["resource_id"]
        if (
            not isinstance(location, str)
            or not location
            or not isinstance(resource, str)
            or not resource
        ):
            raise ProposalRejected(
                "invalid_identifier", "Project step identifiers must be non-empty"
            )
        steps.append(
            ProjectStep(
                _slug(raw["activity_type"], "activity_type"),
                _text(raw["title"], "step title", 4, 100),
                action,
                location,
                None if resource == "none" else resource,
                day,
                hour,
                duration,
            )
        )
    if len({step.title.casefold() for step in steps}) != len(steps):
        raise ProposalRejected("duplicate_steps", "Project steps must be meaningfully distinct")
    ordering = [(step.day_offset, step.scheduled_hour) for step in steps]
    if ordering != sorted(ordering) or len(set(ordering)) != len(ordering):
        raise ProposalRejected("invalid_sequence", "Project steps must be uniquely chronological")
    return SelfProjectCandidate(project_type, title, motivation, float(priority), tuple(steps))


def resolve_self_project(
    candidate: SelfProjectCandidate,
    *,
    proposal_id: str,
    state: PlanningState,
    catalog: WorldCatalog,
    actual_revision: int,
    simulated_at: datetime,
) -> SelfProjectResolution:
    common = {
        "proposal_id": proposal_id,
        "project_type": candidate.project_type,
        "title": candidate.title,
        "motivation": candidate.motivation,
        "step_count": len(candidate.steps),
        "simulated_at": simulated_at.isoformat(),
    }
    proposed = DomainEvent("self_project.proposed", "pathos", common, correlation_id=proposal_id)

    def reject(code: str, explanation: str) -> SelfProjectResolution:
        return SelfProjectResolution(
            False,
            code,
            (
                proposed,
                DomainEvent(
                    "self_project.rejected",
                    "pathos",
                    {**common, "code": code, "explanation": explanation},
                    causation_id=proposed.event_id,
                    correlation_id=proposal_id,
                ),
            ),
        )

    if simulated_at.utcoffset() is None:
        return reject("naive_time", "Project planning needs timezone-aware time")
    intervals: list[tuple[datetime, datetime, str]] = []
    for step in candidate.steps:
        if step.location_id not in catalog.places:
            return reject("unknown_location", "A project step uses an unknown place")
        start = (simulated_at + timedelta(days=step.day_offset)).replace(
            hour=step.scheduled_hour, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(hours=step.duration_hours)
        if not location_allows_interval(step.location_id, start, end, catalog.opening_hours):
            return reject("place_closed", f"The place is closed during {step.title}")
        resource = state.objects.get(step.resource_id) if step.resource_id else None
        if step.resource_id is not None and resource is None:
            return reject("unknown_resource", f"{step.title} needs an unknown object")
        if resource is not None:
            shared = resource.owner_id == resource.custodian_id == "community"
            if resource.custodian_id != "pathos" and not shared:
                return reject(
                    "resource_unavailable", f"Pathos cannot use the object for {step.title}"
                )
            if (
                resource.location_id != step.location_id
                or resource.condition not in {"good", "usable", "repaired"}
                or resource.quantity == 0
            ):
                return reject("resource_unavailable", f"The object is unusable for {step.title}")
        intervals.append((start, end, step.location_id))
    if not _all_fit(intervals, state.calendar.values(), catalog):
        return reject("schedule_conflict", "The project cannot fit around existing time and travel")

    goal_id = f"{proposal_id}-goal"
    accepted = DomainEvent(
        "self_project.accepted",
        "pathos",
        common,
        causation_id=proposed.event_id,
        correlation_id=proposal_id,
    )
    goal = DomainEvent(
        "goal.activated",
        "pathos",
        {
            "goal_id": goal_id,
            "title": candidate.title,
            "motivation": candidate.motivation,
            "source_proposal_id": proposal_id,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=accepted.event_id,
        correlation_id=proposal_id,
    )
    events: list[DomainEvent] = [proposed, accepted, goal]
    for number, (step, interval) in enumerate(zip(candidate.steps, intervals, strict=True), 1):
        start, end, _ = interval
        intention_id = f"{proposal_id}-step-{number}-intention"
        events.append(
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": f"{proposal_id}-step-{number}",
                    "title": step.title,
                    "starts_at": start.isoformat(),
                    "ends_at": end.isoformat(),
                    "location_id": step.location_id,
                    "actor_id": "pathos",
                    "action": step.action.value,
                    "target_id": step.location_id,
                    "goal_id": goal_id,
                    "resource_id": step.resource_id,
                    "activity_type": step.activity_type,
                    "source_proposal_id": proposal_id,
                    "intention_id": intention_id,
                    "goal_progress_delta": 1 / len(candidate.steps),
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=accepted.event_id,
                correlation_id=proposal_id,
            )
        )
    projected = state
    for event in events:
        projected = projected.apply(event)
    for number, step in enumerate(candidate.steps, 1):
        resolution = resolve_intention(
            IntentionProposal(
                proposal_id=f"intend-{proposal_id}-step-{number}",
                intention_id=f"{proposal_id}-step-{number}-intention",
                actor_id="pathos",
                action=step.action,
                motivation=candidate.motivation,
                priority=candidate.priority,
                expected_revision=actual_revision + len(events),
                goal_id=goal_id,
                target_id=step.location_id,
            ),
            state=projected,
            actual_revision=actual_revision + len(events),
            simulated_at=simulated_at,
        )
        if not resolution.accepted:
            return reject("intention_rejected", "A project step could not form an intention")
        events.extend(resolution.events)
        for event in resolution.events:
            projected = projected.apply(event)
    return SelfProjectResolution(True, "accepted", tuple(events))


def _all_fit(
    proposed: list[tuple[datetime, datetime, str]],
    existing: Iterable[CalendarEntry],
    catalog: WorldCatalog,
) -> bool:
    intervals = [
        (
            datetime.fromisoformat(entry.starts_at),
            datetime.fromisoformat(entry.ends_at)
            if entry.ends_at
            else datetime.fromisoformat(entry.starts_at),
            entry.location_id,
        )
        for entry in existing
        if entry.status == "scheduled" and entry.actor_id in {None, "pathos"}
    ]
    combined = sorted([*intervals, *proposed], key=lambda item: item[0])
    for previous, following in zip(combined, combined[1:]):
        previous_start, previous_end, previous_location = previous
        next_start, _, next_location = following
        if previous_start < next_start and previous_end > next_start:
            return False
        try:
            if (
                previous_end
                + route_duration(previous_location, next_location, catalog.route_minutes)
                > next_start
            ):
                return False
        except ValueError:
            return False
    return True


def _slug(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SLUG.fullmatch(value):
        raise ProposalRejected("invalid_slug", f"{field} must be a stable slug")
    return value


def _text(value: object, field: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ProposalRejected("invalid_text", f"{field} length is outside policy")
    if _OUTCOME.search(value):
        raise ProposalRejected("claims_outcome", "A project proposal cannot claim success")
    return value.strip()
