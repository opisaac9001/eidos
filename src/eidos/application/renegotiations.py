"""Carry reflective timing decisions into bounded two-party renegotiation."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence
from uuid import UUID

from eidos.domain.commitments import (
    RenegotiationOfferProposal,
    RenegotiationResponse,
    RenegotiationResponseProposal,
    project_renegotiations,
    resolve_renegotiation_offer,
    resolve_renegotiation_response,
)
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of, kind_index
from eidos.domain.npcs import NPCState
from eidos.domain.planning import CalendarEntry, PlanningState
from eidos.domain.travel import route_duration
from eidos.domain.world import location_allows_interval
from eidos.domain.world_catalog import WorldCatalog


def reflective_renegotiation_offer_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    *,
    planning: PlanningState,
    catalog: WorldCatalog,
) -> list[DomainEvent]:
    """Let one unhandled Pathos decision become a feasible request to its creditor."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Renegotiation time must be timezone-aware")
    negotiations = project_renegotiations(history)
    handled_decisions = {
        str(event.payload["source_decision_event_id"])
        for event in events_of(history, "commitment.reflective_renegotiation_handled")
        if isinstance(event.payload.get("source_decision_event_id"), str)
    }
    decision = next(
        (
            event
            for event in events_of(history, "reflection.reconsideration_decided")
            if event.aggregate_id == "pathos"
            and event.payload.get("target_type") == "commitment"
            and event.payload.get("decision") == "consider_renegotiation"
            and str(event.event_id) not in handled_decisions
        ),
        None,
    )
    if decision is None:
        return []
    commitment_id = decision.payload.get("target_id")
    if not isinstance(commitment_id, str):
        return [_handled(decision, simulated_at, "invalid_target")]
    created = kind_index(history).latest(
        "commitment.created",
        lambda event: (
            event.aggregate_id == "pathos"
            and event.payload.get("commitment_id") == commitment_id
            and event.payload.get("debtor_id") == "pathos"
        ),
    )
    commitment = planning.commitments.get(commitment_id)
    linked = [
        entry
        for entry in planning.calendar.values()
        if entry.commitment_id == commitment_id and entry.status in {"scheduled", "interrupted"}
    ]
    if created is None or commitment is None or commitment.status != "active" or len(linked) != 1:
        return [_handled(decision, simulated_at, "commitment_no_longer_eligible")]
    interval = next_feasible_interval(linked[0], planning, simulated_at, catalog)
    if interval is None:
        return [_handled(decision, simulated_at, "no_feasible_time")]
    starts_at, ends_at = interval
    old_due = datetime.fromisoformat(commitment.due_at)
    due_at = old_due if ends_at <= old_due else ends_at + timedelta(days=1)
    offer_id = f"reflective-offer-{decision.event_id}"
    resolution = resolve_renegotiation_offer(
        RenegotiationOfferProposal(
            proposal_id=f"propose-{offer_id}",
            offer_id=offer_id,
            commitment_id=commitment_id,
            actor_id="pathos",
            due_at=due_at,
            starts_at=starts_at,
            ends_at=ends_at,
            reason="The earlier work was interrupted, so Pathos asked for a workable new time.",
            expected_revision=actual_revision,
        ),
        planning=planning,
        negotiations=negotiations,
        actual_revision=actual_revision,
        simulated_at=simulated_at,
        opening_hours=catalog.opening_hours,
    )
    handled = _handled(
        decision,
        simulated_at,
        "offer_sent" if resolution.accepted else f"offer_{resolution.code}",
        causation_id=resolution.events[-1].event_id,
    )
    return [*resolution.events, handled]


def renegotiation_response_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    *,
    planning: PlanningState,
    catalog: WorldCatalog,
    npc_people: Mapping[str, NPCState],
) -> list[DomainEvent]:
    """Let one creditor independently answer an old-enough pending offer."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Renegotiation response time must be timezone-aware")
    if not 8 <= simulated_at.hour < 22:
        return []
    negotiations = project_renegotiations(history)
    handled_offers = {
        str(event.payload["offer_id"])
        for event in events_of(history, "commitment.reflective_renegotiation_response_handled")
        if isinstance(event.payload.get("offer_id"), str)
    }
    offer = next(
        (
            item
            for item in negotiations.offers.values()
            if item.status == "pending"
            and item.offer_id not in handled_offers
            and item.awaiting_actor_id in npc_people
            and _response_due(history, item.offer_id) <= simulated_at
        ),
        None,
    )
    if offer is None:
        return []
    person = npc_people[offer.awaiting_actor_id]
    capacity = 0.1 + 0.15 * person.energy + 0.25 * person.connection + 0.35 * person.purpose
    accepts = _sample(offer.offer_id) < max(0.05, min(0.9, capacity))
    response = RenegotiationResponse.ACCEPT if accepts else RenegotiationResponse.DECLINE
    resolution = resolve_renegotiation_response(
        RenegotiationResponseProposal(
            proposal_id=f"respond-{offer.offer_id}",
            offer_id=offer.offer_id,
            actor_id=offer.awaiting_actor_id,
            response=response,
            reason=(
                "The new timing works for me."
                if accepts
                else "That change does not work for me, so the existing agreement stands."
            ),
            expected_revision=actual_revision,
        ),
        planning=planning,
        negotiations=negotiations,
        actual_revision=actual_revision,
        simulated_at=simulated_at,
        opening_hours=catalog.opening_hours,
    )
    handled = DomainEvent(
        "commitment.reflective_renegotiation_response_handled",
        "pathos",
        {
            "offer_id": offer.offer_id,
            "actor_id": offer.awaiting_actor_id,
            "outcome": resolution.code,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=resolution.events[-1].event_id,
        correlation_id=offer.offer_id,
    )
    return [*resolution.events, handled]


def next_feasible_interval(
    entry: CalendarEntry,
    planning: PlanningState,
    simulated_at: datetime,
    catalog: WorldCatalog,
) -> tuple[datetime, datetime] | None:
    if entry.location_id not in catalog.places:
        return None
    original_start = datetime.fromisoformat(entry.starts_at)
    original_end = datetime.fromisoformat(entry.ends_at) if entry.ends_at else original_start
    duration = max(timedelta(hours=1), original_end - original_start)
    place = catalog.places[entry.location_id]
    day = (simulated_at + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    for day_offset in range(14):
        for hour in range(place.opens_hour, place.closes_hour):
            start = day + timedelta(days=day_offset, hours=hour)
            end = start + duration
            if _fits(entry, start, end, planning, catalog):
                return start, end
    return None


def _fits(
    entry: CalendarEntry,
    start: datetime,
    end: datetime,
    planning: PlanningState,
    catalog: WorldCatalog,
) -> bool:
    if not location_allows_interval(entry.location_id, start, end, catalog.opening_hours):
        return False
    for other in planning.calendar.values():
        if (
            other.schedule_id == entry.schedule_id
            or other.status != "scheduled"
            or other.actor_id not in {None, "pathos"}
        ):
            continue
        other_start = datetime.fromisoformat(other.starts_at)
        other_end = datetime.fromisoformat(other.ends_at) if other.ends_at else other_start
        if start < other_end and other_start < end:
            return False
        try:
            if other_end <= start and (
                other_end
                + route_duration(other.location_id, entry.location_id, catalog.route_minutes)
                > start
            ):
                return False
            if end <= other_start and (
                end + route_duration(entry.location_id, other.location_id, catalog.route_minutes)
                > other_start
            ):
                return False
        except ValueError:
            return False
    return True


def _response_due(history: Sequence[DomainEvent], offer_id: str) -> datetime:
    offered = next(
        event
        for event in events_of(history, "commitment.renegotiation_offered")
        if event.payload.get("offer_id") == offer_id
    )
    offered_at = datetime.fromisoformat(str(offered.payload["simulated_at"]))
    delay_hours = 1 + int(_sample(f"response-delay-{offer_id}") * 5)
    return offered_at + timedelta(hours=delay_hours)


def _handled(
    decision: DomainEvent,
    simulated_at: datetime,
    outcome: str,
    *,
    causation_id: UUID | None = None,
) -> DomainEvent:
    return DomainEvent(
        "commitment.reflective_renegotiation_handled",
        "pathos",
        {
            "source_decision_event_id": str(decision.event_id),
            "commitment_id": decision.payload.get("target_id"),
            "outcome": outcome,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=causation_id or decision.event_id,
        correlation_id=decision.correlation_id,
    )


def _sample(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
