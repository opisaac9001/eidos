"""Carry a completed personal schedule review into validated replanning."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from eidos.application.renegotiations import next_feasible_interval
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of, kind_index
from eidos.domain.planning import PlanningState
from eidos.domain.rescheduling import RescheduleProposal, resolve_reschedule
from eidos.domain.world_catalog import WorldCatalog


def reflective_rescheduling_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    *,
    planning: PlanningState,
    catalog: WorldCatalog,
) -> list[DomainEvent]:
    """Resolve one unhandled `seek_new_time` decision for Pathos-owned work."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Reflective rescheduling time must be timezone-aware")
    handled = {
        str(event.payload["source_decision_event_id"])
        for event in events_of(history, "schedule.reflective_rescheduling_handled")
        if isinstance(event.payload.get("source_decision_event_id"), str)
    }
    decision = next(
        (
            event
            for event in events_of(history, "reflection.reconsideration_decided")
            if event.aggregate_id == "pathos"
            and event.payload.get("target_type") == "schedule"
            and event.payload.get("decision") == "seek_new_time"
            and str(event.event_id) not in handled
        ),
        None,
    )
    if decision is None:
        return []
    schedule_id = decision.payload.get("target_id")
    created = kind_index(history).latest(
        "schedule.created",
        lambda event: (
            event.aggregate_id == "pathos" and event.payload.get("schedule_id") == schedule_id
        ),
    )
    entry = planning.calendar.get(schedule_id) if isinstance(schedule_id, str) else None
    if (
        created is None
        or entry is None
        or entry.status != "interrupted"
        or entry.commitment_id is not None
    ):
        return [_handled(decision, simulated_at, "schedule_no_longer_eligible")]
    interval = next_feasible_interval(entry, planning, simulated_at, catalog)
    if interval is None:
        return [_handled(decision, simulated_at, "no_feasible_time")]
    starts_at, ends_at = interval
    resolution = resolve_reschedule(
        RescheduleProposal(
            proposal_id=f"reflective-reschedule-{decision.event_id}",
            schedule_id=entry.schedule_id,
            actor_id="pathos",
            starts_at=starts_at,
            ends_at=ends_at,
            reason="After reconsidering the interruption, Pathos chose a workable new time.",
            expected_revision=actual_revision,
        ),
        planning=planning,
        actual_revision=actual_revision,
        simulated_at=simulated_at,
        opening_hours=catalog.opening_hours,
        route_minutes=catalog.route_minutes,
    )
    return [
        *resolution.events,
        _handled(
            decision,
            simulated_at,
            "rescheduled" if resolution.accepted else f"reschedule_{resolution.code}",
            cause=resolution.events[-1],
        ),
    ]


def _handled(
    decision: DomainEvent,
    simulated_at: datetime,
    outcome: str,
    *,
    cause: DomainEvent | None = None,
) -> DomainEvent:
    return DomainEvent(
        "schedule.reflective_rescheduling_handled",
        "pathos",
        {
            "source_decision_event_id": str(decision.event_id),
            "schedule_id": decision.payload.get("target_id"),
            "outcome": outcome,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=(cause or decision).event_id,
        correlation_id=decision.correlation_id,
    )
