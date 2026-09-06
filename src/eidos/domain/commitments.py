"""Two-party, feasible renegotiation of an existing commitment and schedule."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState
from eidos.domain.world import location_allows_interval


class RenegotiationResponse(StrEnum):
    ACCEPT = "accept"
    DECLINE = "decline"


@dataclass(frozen=True, slots=True)
class RenegotiationOffer:
    offer_id: str
    commitment_id: str
    proposed_by_id: str
    awaiting_actor_id: str
    due_at: str
    starts_at: str
    ends_at: str
    reason: str
    status: str = "pending"


@dataclass(frozen=True, slots=True)
class RenegotiationState:
    offers: Mapping[str, RenegotiationOffer]

    def __post_init__(self) -> None:
        object.__setattr__(self, "offers", MappingProxyType(dict(self.offers)))

    def apply(self, event: DomainEvent) -> RenegotiationState:
        offers = dict(self.offers)
        payload = event.payload
        if event.kind == "commitment.renegotiation_offered":
            offer_id = _required(payload, "offer_id")
            if offer_id in offers:
                raise ValueError("Renegotiation offer already exists")
            offers[offer_id] = RenegotiationOffer(
                offer_id,
                _required(payload, "commitment_id"),
                _required(payload, "proposed_by_id"),
                _required(payload, "awaiting_actor_id"),
                _required(payload, "due_at"),
                _required(payload, "starts_at"),
                _required(payload, "ends_at"),
                _required(payload, "reason"),
            )
        elif event.kind in {
            "commitment.renegotiation_accepted",
            "commitment.renegotiation_declined",
        }:
            offer = offers.get(_required(payload, "offer_id"))
            if offer is None or offer.status != "pending":
                raise ValueError("Renegotiation offer is not pending")
            if _required(payload, "actor_id") != offer.awaiting_actor_id:
                raise ValueError("Only the awaited creditor can answer")
            offers[offer.offer_id] = replace(
                offer, status="accepted" if event.kind.endswith("accepted") else "declined"
            )
        return RenegotiationState(offers)


@dataclass(frozen=True, slots=True)
class RenegotiationOfferProposal:
    proposal_id: str
    offer_id: str
    commitment_id: str
    actor_id: str
    due_at: datetime
    starts_at: datetime
    ends_at: datetime
    reason: str
    expected_revision: int
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class RenegotiationResponseProposal:
    proposal_id: str
    offer_id: str
    actor_id: str
    response: RenegotiationResponse
    reason: str
    expected_revision: int
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class RenegotiationResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


def resolve_renegotiation_offer(
    proposal: RenegotiationOfferProposal,
    *,
    planning: PlanningState,
    negotiations: RenegotiationState,
    actual_revision: int,
    simulated_at: datetime,
    opening_hours: Mapping[str, tuple[time, time]] | None = None,
) -> RenegotiationResolution:
    common = {
        "proposal_id": proposal.proposal_id,
        "offer_id": proposal.offer_id,
        "commitment_id": proposal.commitment_id,
        "proposed_by_id": proposal.actor_id,
        "due_at": proposal.due_at.isoformat(),
        "starts_at": proposal.starts_at.isoformat(),
        "ends_at": proposal.ends_at.isoformat(),
        "reason": proposal.reason,
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at.isoformat(),
    }
    proposed = DomainEvent(
        "commitment.renegotiation_proposed",
        "pathos",
        common,
        correlation_id=proposal.proposal_id,
    )

    def reject(code: str, explanation: str) -> RenegotiationResolution:
        return RenegotiationResolution(
            False,
            code,
            (
                proposed,
                _effect(
                    "commitment.renegotiation_rejected",
                    {**common, "code": code, "explanation": explanation},
                    proposed,
                ),
            ),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The plan changed before renegotiation")
    if proposal.schema_version != 1:
        return reject("unsupported_schema", "Renegotiation schema is not supported")
    if any(
        not value.strip()
        for value in (
            proposal.proposal_id,
            proposal.offer_id,
            proposal.commitment_id,
            proposal.actor_id,
            proposal.reason,
        )
    ):
        return reject("invalid_text", "Renegotiation identifiers and reason are required")
    if proposal.offer_id in negotiations.offers:
        return reject("duplicate_offer", "That renegotiation already exists")
    commitment = planning.commitments.get(proposal.commitment_id)
    if commitment is None:
        return reject("unknown_commitment", "The commitment does not exist")
    if commitment.status != "active":
        return reject("closed_commitment", "Only an active commitment can change")
    if proposal.actor_id != commitment.debtor_id:
        return reject("wrong_actor", "Only the responsible debtor can propose new terms")
    if any(
        value.utcoffset() is None
        for value in (proposal.due_at, proposal.starts_at, proposal.ends_at, simulated_at)
    ):
        return reject("invalid_time", "Renegotiation times require timezones")
    if not simulated_at < proposal.starts_at < proposal.ends_at <= proposal.due_at:
        return reject("infeasible_interval", "New work must fit before the proposed deadline")
    entries = [
        entry
        for entry in planning.calendar.values()
        if entry.commitment_id == commitment.commitment_id
        and entry.status in {"scheduled", "interrupted"}
    ]
    if len(entries) != 1:
        return reject("missing_schedule", "Renegotiation requires one unfinished linked schedule")
    entry = entries[0]
    if not location_allows_interval(
        entry.location_id, proposal.starts_at, proposal.ends_at, opening_hours
    ):
        return reject("location_closed", "The new interval falls outside opening hours")
    for other in planning.calendar.values():
        if other.schedule_id == entry.schedule_id or other.status != "scheduled":
            continue
        other_start = datetime.fromisoformat(other.starts_at)
        other_end = datetime.fromisoformat(other.ends_at) if other.ends_at else other_start
        if proposal.starts_at < other_end and other_start < proposal.ends_at:
            return reject("schedule_conflict", f"The new interval overlaps {other.title}")
    offered = _effect(
        "commitment.renegotiation_offered",
        {**common, "awaiting_actor_id": commitment.creditor_id},
        proposed,
    )
    return RenegotiationResolution(True, "accepted", (proposed, offered))


def resolve_renegotiation_response(
    proposal: RenegotiationResponseProposal,
    *,
    planning: PlanningState,
    negotiations: RenegotiationState,
    actual_revision: int,
    simulated_at: datetime,
    opening_hours: Mapping[str, tuple[time, time]] | None = None,
) -> RenegotiationResolution:
    common = {
        "proposal_id": proposal.proposal_id,
        "offer_id": proposal.offer_id,
        "actor_id": proposal.actor_id,
        "response": proposal.response.value,
        "reason": proposal.reason,
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at.isoformat(),
    }
    proposed = DomainEvent(
        "commitment.renegotiation_response_proposed",
        "pathos",
        common,
        correlation_id=proposal.proposal_id,
    )

    def reject(code: str, explanation: str) -> RenegotiationResolution:
        return RenegotiationResolution(
            False,
            code,
            (
                proposed,
                _effect(
                    "commitment.renegotiation_response_rejected",
                    {**common, "code": code, "explanation": explanation},
                    proposed,
                ),
            ),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The plan changed before the response")
    if proposal.schema_version != 1:
        return reject("unsupported_schema", "Renegotiation schema is not supported")
    if any(
        not value.strip()
        for value in (proposal.proposal_id, proposal.offer_id, proposal.actor_id, proposal.reason)
    ):
        return reject("invalid_text", "Response identifiers and reason are required")
    offer = negotiations.offers.get(proposal.offer_id)
    if offer is None or offer.status != "pending":
        return reject("closed_offer", "The renegotiation offer is not pending")
    if proposal.actor_id != offer.awaiting_actor_id:
        return reject("wrong_actor", "Only the creditor can answer the offer")
    commitment = planning.commitments.get(offer.commitment_id)
    if commitment is None or commitment.status != "active":
        return reject("closed_commitment", "The linked commitment is no longer active")
    entry = next(
        (
            item
            for item in planning.calendar.values()
            if item.commitment_id == commitment.commitment_id
            and item.status in {"scheduled", "interrupted"}
        ),
        None,
    )
    if entry is None:
        return reject("missing_schedule", "The linked schedule is no longer available")
    resolved_kind = (
        "commitment.renegotiation_accepted"
        if proposal.response is RenegotiationResponse.ACCEPT
        else "commitment.renegotiation_declined"
    )
    resolved = _effect(resolved_kind, common, proposed)
    if proposal.response is RenegotiationResponse.DECLINE:
        return RenegotiationResolution(True, "declined", (proposed, resolved))
    starts_at = datetime.fromisoformat(offer.starts_at)
    ends_at = datetime.fromisoformat(offer.ends_at)
    due_at = datetime.fromisoformat(offer.due_at)
    if not simulated_at < starts_at < ends_at <= due_at:
        return reject("infeasible_interval", "The proposed interval is no longer feasible")
    if not location_allows_interval(entry.location_id, starts_at, ends_at, opening_hours):
        return reject("location_closed", "The proposed location is unavailable at that time")
    for other in planning.calendar.values():
        if other.schedule_id == entry.schedule_id or other.status != "scheduled":
            continue
        other_start = datetime.fromisoformat(other.starts_at)
        other_end = datetime.fromisoformat(other.ends_at) if other.ends_at else other_start
        if starts_at < other_end and other_start < ends_at:
            return reject("schedule_conflict", "Another plan now occupies the proposed interval")
    changed = _effect(
        "commitment.renegotiated",
        {
            "commitment_id": commitment.commitment_id,
            "actor_id": proposal.actor_id,
            "from_due_at": commitment.due_at,
            "due_at": offer.due_at,
            "terms_version": commitment.terms_version + 1,
            "reason": offer.reason,
            "simulated_at": simulated_at.isoformat(),
        },
        resolved,
    )
    retimed = _effect(
        "schedule.retimed",
        {
            "schedule_id": entry.schedule_id,
            "from_starts_at": entry.starts_at,
            "starts_at": offer.starts_at,
            "ends_at": offer.ends_at,
            "reason": offer.reason,
            "simulated_at": simulated_at.isoformat(),
        },
        resolved,
    )
    return RenegotiationResolution(True, "accepted", (proposed, resolved, changed, retimed))


def project_renegotiations(events: Sequence[DomainEvent]) -> RenegotiationState:
    state = RenegotiationState({})
    for event in events:
        state = state.apply(event)
    return state


def _effect(kind: str, payload: Mapping[str, Any], cause: DomainEvent) -> DomainEvent:
    return DomainEvent(
        kind,
        "pathos",
        payload,
        causation_id=cause.event_id,
        correlation_id=cause.correlation_id,
    )


def _required(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value
