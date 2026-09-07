"""Validated retiming of interrupted Pathos-owned personal activities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Mapping

from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState
from eidos.domain.travel import route_duration
from eidos.domain.world import location_allows_interval


@dataclass(frozen=True, slots=True)
class RescheduleProposal:
    proposal_id: str
    schedule_id: str
    actor_id: str
    starts_at: datetime
    ends_at: datetime
    reason: str
    expected_revision: int
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class RescheduleResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


@dataclass(frozen=True, slots=True)
class ScheduleCancellationProposal:
    proposal_id: str
    schedule_id: str
    actor_id: str
    reason: str
    expected_revision: int
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class ScheduleCancellationResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


def resolve_reschedule(
    proposal: RescheduleProposal,
    *,
    planning: PlanningState,
    actual_revision: int,
    simulated_at: datetime,
    opening_hours: Mapping[str, tuple[time, time]] | None = None,
    route_minutes: Mapping[frozenset[str], int] | None = None,
) -> RescheduleResolution:
    """Validate one personal reschedule without changing an external agreement."""
    common = {
        "proposal_id": proposal.proposal_id,
        "schedule_id": proposal.schedule_id,
        "actor_id": proposal.actor_id,
        "starts_at": proposal.starts_at.isoformat(),
        "ends_at": proposal.ends_at.isoformat(),
        "reason": proposal.reason,
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at.isoformat(),
    }
    proposed = DomainEvent(
        "schedule.reschedule_proposed",
        "pathos",
        common,
        correlation_id=proposal.proposal_id,
    )

    def reject(code: str, explanation: str) -> RescheduleResolution:
        return RescheduleResolution(
            False,
            code,
            (
                proposed,
                _effect(
                    "schedule.reschedule_rejected",
                    {**common, "code": code, "explanation": explanation},
                    proposed,
                ),
            ),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The calendar changed before rescheduling")
    if proposal.schema_version != 1:
        return reject("unsupported_schema", "Rescheduling schema is not supported")
    if any(
        not value.strip()
        for value in (
            proposal.proposal_id,
            proposal.schedule_id,
            proposal.actor_id,
            proposal.reason,
        )
    ):
        return reject("invalid_text", "Rescheduling identifiers and reason are required")
    entry = planning.calendar.get(proposal.schedule_id)
    if entry is None:
        return reject("unknown_schedule", "The scheduled activity does not exist")
    if entry.status != "interrupted":
        return reject("not_interrupted", "Only interrupted activity can be rescheduled")
    if proposal.actor_id != "pathos" or entry.actor_id not in {None, proposal.actor_id}:
        return reject("wrong_actor", "Only the activity owner can reschedule it")
    if entry.commitment_id is not None:
        return reject("external_commitment", "Externally owed work requires renegotiation")
    if any(
        value.utcoffset() is None for value in (simulated_at, proposal.starts_at, proposal.ends_at)
    ):
        return reject("invalid_time", "Rescheduling times require timezones")
    if not simulated_at < proposal.starts_at < proposal.ends_at:
        return reject("invalid_interval", "The replacement interval must be in the future")
    old_start = datetime.fromisoformat(entry.starts_at)
    old_end = datetime.fromisoformat(entry.ends_at) if entry.ends_at else old_start + _ONE_HOUR
    if proposal.ends_at - proposal.starts_at != old_end - old_start:
        return reject("changed_duration", "Rescheduling must preserve the activity duration")
    if not location_allows_interval(
        entry.location_id, proposal.starts_at, proposal.ends_at, opening_hours
    ):
        return reject("location_closed", "The replacement interval is outside opening hours")
    for other in planning.calendar.values():
        if (
            other.schedule_id == entry.schedule_id
            or other.status != "scheduled"
            or other.actor_id not in {None, "pathos"}
        ):
            continue
        other_start = datetime.fromisoformat(other.starts_at)
        other_end = datetime.fromisoformat(other.ends_at) if other.ends_at else other_start
        if proposal.starts_at < other_end and other_start < proposal.ends_at:
            return reject("schedule_conflict", f"The replacement overlaps {other.title}")
        try:
            if other_end <= proposal.starts_at and (
                other_end + route_duration(other.location_id, entry.location_id, route_minutes)
                > proposal.starts_at
            ):
                return reject(
                    "travel_conflict", f"There is not enough travel time after {other.title}"
                )
            if proposal.ends_at <= other_start and (
                proposal.ends_at
                + route_duration(entry.location_id, other.location_id, route_minutes)
                > other_start
            ):
                return reject(
                    "travel_conflict", f"There is not enough travel time before {other.title}"
                )
        except ValueError:
            return reject("unknown_route", "The replacement interval requires an unknown route")
    accepted = _effect("schedule.reschedule_accepted", common, proposed)
    changed = _effect(
        "schedule.rescheduled",
        {
            "schedule_id": entry.schedule_id,
            "from_starts_at": entry.starts_at,
            "starts_at": proposal.starts_at.isoformat(),
            "ends_at": proposal.ends_at.isoformat(),
            "reason": proposal.reason,
            "simulated_at": simulated_at.isoformat(),
        },
        accepted,
    )
    return RescheduleResolution(True, "accepted", (proposed, accepted, changed))


def resolve_schedule_cancellation(
    proposal: ScheduleCancellationProposal,
    *,
    planning: PlanningState,
    actual_revision: int,
    simulated_at: datetime,
) -> ScheduleCancellationResolution:
    """Release one interrupted optional activity and its own active intention."""
    common = {
        "proposal_id": proposal.proposal_id,
        "schedule_id": proposal.schedule_id,
        "actor_id": proposal.actor_id,
        "reason": proposal.reason,
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at.isoformat(),
    }
    proposed = DomainEvent(
        "schedule.cancellation_proposed",
        "pathos",
        common,
        correlation_id=proposal.proposal_id,
    )

    def reject(code: str, explanation: str) -> ScheduleCancellationResolution:
        return ScheduleCancellationResolution(
            False,
            code,
            (
                proposed,
                _effect(
                    "schedule.cancellation_rejected",
                    {**common, "code": code, "explanation": explanation},
                    proposed,
                ),
            ),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The calendar changed before cancellation")
    if proposal.schema_version != 1:
        return reject("unsupported_schema", "Cancellation schema is not supported")
    if any(
        not value.strip()
        for value in (
            proposal.proposal_id,
            proposal.schedule_id,
            proposal.actor_id,
            proposal.reason,
        )
    ):
        return reject("invalid_text", "Cancellation identifiers and reason are required")
    if simulated_at.utcoffset() is None:
        return reject("invalid_time", "Cancellation time requires a timezone")
    entry = planning.calendar.get(proposal.schedule_id)
    if entry is None:
        return reject("unknown_schedule", "The scheduled activity does not exist")
    if entry.status != "interrupted":
        return reject("not_interrupted", "Only interrupted activity can be released here")
    if proposal.actor_id != "pathos" or entry.actor_id not in {None, proposal.actor_id}:
        return reject("wrong_actor", "Only the activity owner can release it")
    if entry.commitment_id is not None:
        return reject("external_commitment", "Externally owed work cannot be released privately")
    if entry.goal_id is not None:
        return reject("linked_goal", "Goal work must be reconsidered through its whole goal")
    intention = (
        planning.intentions.get(entry.intention_id) if entry.intention_id is not None else None
    )
    if entry.intention_id is not None and (
        intention is None or intention.status != "active" or intention.actor_id != "pathos"
    ):
        return reject("closed_intention", "The linked intention is not available to release")
    accepted = _effect("schedule.cancellation_accepted", common, proposed)
    cancelled = _effect(
        "schedule.cancelled",
        {
            "schedule_id": entry.schedule_id,
            "reason": proposal.reason,
            "simulated_at": simulated_at.isoformat(),
        },
        accepted,
    )
    events = [proposed, accepted, cancelled]
    if intention is not None:
        events.append(
            _effect(
                "intention.abandoned",
                {
                    "intention_id": intention.intention_id,
                    "reason": proposal.reason,
                    "simulated_at": simulated_at.isoformat(),
                },
                accepted,
            )
        )
    return ScheduleCancellationResolution(True, "accepted", tuple(events))


_ONE_HOUR = timedelta(hours=1)


def _effect(kind: str, payload: Mapping[str, Any], cause: DomainEvent) -> DomainEvent:
    return DomainEvent(
        kind,
        "pathos",
        payload,
        causation_id=cause.event_id,
        correlation_id=cause.correlation_id,
    )
