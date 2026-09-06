"""Typed route traversal preventing uncaused or impossibly fast movement."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Sequence
from uuid import UUID

from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected
from eidos.domain.world_catalog import SEED_ROUTE_MINUTES

ROUTE_MINUTES = SEED_ROUTE_MINUTES


@dataclass(frozen=True, slots=True)
class TravelProposal:
    proposal_id: str
    actor_id: str
    origin_id: str
    destination_id: str
    depart_at: datetime
    arrive_at: datetime
    expected_revision: int
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class TravelResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


_FIELDS = {
    "schema_version",
    "proposal_id",
    "actor_id",
    "origin_id",
    "destination_id",
    "depart_at",
    "arrive_at",
    "expected_revision",
}


def route_duration(
    origin_id: str,
    destination_id: str,
    route_minutes: Mapping[frozenset[str], int] = ROUTE_MINUTES,
) -> timedelta:
    if origin_id == destination_id:
        return timedelta(0)
    minutes = route_minutes.get(frozenset((origin_id, destination_id)))
    if minutes is None:
        raise ValueError("No route connects those locations")
    return timedelta(minutes=minutes)


def parse_travel_proposal(content: str) -> TravelProposal:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "Travel proposal was not valid JSON") from None
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ProposalRejected("invalid_shape", "Travel fields did not match schema v1")
    if value["schema_version"] != 1:
        raise ProposalRejected("unsupported_schema", "Travel schema is not supported")
    for field in ("proposal_id", "actor_id", "origin_id", "destination_id"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ProposalRejected("invalid_text", f"{field} must be non-empty")
    revision = value["expected_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ProposalRejected("invalid_revision", "expected_revision must be non-negative")
    times = []
    for field in ("depart_at", "arrive_at"):
        try:
            parsed = datetime.fromisoformat(value[field])
        except (TypeError, ValueError):
            raise ProposalRejected("invalid_time", f"{field} must be ISO time") from None
        if parsed.utcoffset() is None:
            raise ProposalRejected("invalid_time", f"{field} needs a timezone")
        times.append(parsed)
    return TravelProposal(
        proposal_id=value["proposal_id"],
        actor_id=value["actor_id"],
        origin_id=value["origin_id"],
        destination_id=value["destination_id"],
        depart_at=times[0],
        arrive_at=times[1],
        expected_revision=revision,
    )


def resolve_travel(
    proposal: TravelProposal,
    *,
    history: Sequence[DomainEvent],
    actor_location_id: str,
    known_location_ids: set[str],
    actual_revision: int,
    simulated_at: datetime,
    route_minutes: Mapping[frozenset[str], int] = ROUTE_MINUTES,
) -> TravelResolution:
    common: dict[str, object] = {
        "proposal_id": proposal.proposal_id,
        "actor_id": proposal.actor_id,
        "origin_id": proposal.origin_id,
        "destination_id": proposal.destination_id,
        "depart_at": proposal.depart_at.isoformat(),
        "arrive_at": proposal.arrive_at.isoformat(),
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at.isoformat(),
    }
    proposed = DomainEvent("travel.proposed", "pathos", common, correlation_id=proposal.proposal_id)

    def effect(
        kind: str, extra: Mapping[str, object], cause: UUID = proposed.event_id
    ) -> DomainEvent:
        return DomainEvent(
            kind,
            "pathos",
            {**common, **extra},
            causation_id=cause,
            correlation_id=proposal.proposal_id,
        )

    def reject(code: str, explanation: str) -> TravelResolution:
        return TravelResolution(
            False,
            code,
            (proposed, effect("travel.rejected", {"code": code, "explanation": explanation})),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The world changed before travel")
    if proposal.actor_id != "pathos":
        return reject("wrong_actor", "This route resolver controls Pathos travel only")
    if proposal.origin_id == proposal.destination_id:
        return reject("already_there", "Travel needs a different destination")
    if {proposal.origin_id, proposal.destination_id} - known_location_ids:
        return reject("unknown_location", "Travel refers to an unknown location")
    if actor_location_id != proposal.origin_id:
        return reject("wrong_origin", "The actor is not at the proposed origin")
    if proposal.arrive_at != simulated_at or proposal.depart_at >= proposal.arrive_at:
        return reject("invalid_window", "Arrival must match current time and follow departure")
    try:
        minimum = route_duration(proposal.origin_id, proposal.destination_id, route_minutes)
    except ValueError:
        return reject("no_route", "No route connects those locations")
    if proposal.arrive_at - proposal.depart_at < minimum:
        return reject("too_fast", "The proposed trip is shorter than its route allows")
    if any(
        event.kind == "travel.completed"
        and event.payload.get("proposal_id") == proposal.proposal_id
        for event in history
    ):
        return reject("duplicate_proposal", "This trip already completed")
    started = effect(
        "travel.started",
        {"minimum_minutes": int(minimum.total_seconds() / 60)},
    )
    completed = effect(
        "travel.completed",
        {"duration_minutes": int((proposal.arrive_at - proposal.depart_at).total_seconds() / 60)},
        started.event_id,
    )
    moved = effect(
        "pathos.moved",
        {"location_id": proposal.destination_id},
        completed.event_id,
    )
    return TravelResolution(True, "accepted", (proposed, started, completed, moved))
