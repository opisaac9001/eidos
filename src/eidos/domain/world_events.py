"""Typed director proposals with pacing and world-side scheduling rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected


class WorldEventKind(StrEnum):
    WEATHER = "weather"
    COMMUNITY = "community"
    AMBIENT = "ambient"


@dataclass(frozen=True, slots=True)
class WorldEventProposal:
    proposal_id: str
    director_id: str
    event_kind: WorldEventKind
    description: str
    location_id: str
    starts_at: datetime
    intensity: float
    expected_revision: int
    source: str
    schema_version: int = 1


@dataclass(frozen=True, slots=True)
class WorldEventResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


_FIELDS = {
    "schema_version",
    "proposal_id",
    "director_id",
    "event_kind",
    "description",
    "location_id",
    "starts_at",
    "intensity",
    "expected_revision",
    "source",
}
_WEATHER = {"Clear", "Cloudy", "Light rain", "Breezy"}


def parse_world_event_proposal(content: str) -> WorldEventProposal:
    try:
        value = json.loads(content)
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_json", "World-event proposal was not valid JSON") from None
    if not isinstance(value, dict) or set(value) != _FIELDS:
        raise ProposalRejected("invalid_shape", "World-event fields did not match schema v1")
    if value["schema_version"] != 1:
        raise ProposalRejected("unsupported_schema", "World-event schema is not supported")
    for field in ("proposal_id", "director_id", "description", "location_id", "source"):
        if not isinstance(value[field], str) or not value[field].strip():
            raise ProposalRejected("invalid_text", f"{field} must be a non-empty string")
    revision = value["expected_revision"]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise ProposalRejected("invalid_revision", "expected_revision must be non-negative")
    intensity = value["intensity"]
    if (
        isinstance(intensity, bool)
        or not isinstance(intensity, (int, float))
        or not 0 <= intensity <= 1
    ):
        raise ProposalRejected("invalid_intensity", "intensity must be between zero and one")
    try:
        kind = WorldEventKind(value["event_kind"])
    except (TypeError, ValueError):
        raise ProposalRejected("unknown_world_event", "World-event kind is not supported") from None
    try:
        starts_at = datetime.fromisoformat(value["starts_at"])
    except (TypeError, ValueError):
        raise ProposalRejected("invalid_start", "starts_at must be an ISO timestamp") from None
    if starts_at.utcoffset() is None:
        raise ProposalRejected("invalid_start", "starts_at must include a timezone")
    return WorldEventProposal(
        proposal_id=value["proposal_id"],
        director_id=value["director_id"],
        event_kind=kind,
        description=value["description"],
        location_id=value["location_id"],
        starts_at=starts_at,
        intensity=float(intensity),
        expected_revision=revision,
        source=value["source"],
    )


def resolve_world_event(
    proposal: WorldEventProposal,
    *,
    history: Sequence[DomainEvent],
    known_location_ids: set[str],
    actual_revision: int,
    simulated_at: datetime,
) -> WorldEventResolution:
    common = {
        "proposal_id": proposal.proposal_id,
        "event_kind": proposal.event_kind.value,
        "description": proposal.description,
        "location_id": proposal.location_id,
        "starts_at": proposal.starts_at.isoformat(),
        "intensity": proposal.intensity,
        "schema_version": proposal.schema_version,
        "simulated_at": simulated_at.isoformat(),
        "source": proposal.source,
    }
    proposed = DomainEvent(
        "world_event.proposed",
        "pathos",
        common,
        correlation_id=proposal.proposal_id,
    )

    def effect(kind: str, payload: Mapping[str, Any]) -> DomainEvent:
        return DomainEvent(
            kind,
            "pathos",
            payload,
            causation_id=proposed.event_id,
            correlation_id=proposal.proposal_id,
        )

    def reject(code: str, explanation: str) -> WorldEventResolution:
        return WorldEventResolution(
            False,
            code,
            (
                proposed,
                effect(
                    "world_event.rejected", {**common, "code": code, "explanation": explanation}
                ),
            ),
        )

    if proposal.expected_revision != actual_revision:
        return reject("stale_revision", "The world changed after this event was proposed")
    if proposal.location_id not in known_location_ids:
        return reject("unknown_location", "The proposed location does not exist")
    if proposal.starts_at < simulated_at:
        return reject("past_start", "A world event cannot begin in the past")
    if proposal.event_kind in {WorldEventKind.COMMUNITY, WorldEventKind.AMBIENT} and (
        proposal.starts_at < simulated_at + timedelta(hours=1)
        and proposal.source != "causal-world-response"
    ):
        return reject(
            "insufficient_lead_time", "Scheduled events need at least one hour of lead time"
        )
    if proposal.event_kind is WorldEventKind.WEATHER and proposal.description not in _WEATHER:
        return reject("invalid_weather", "Weather is outside the world's vocabulary")
    last_same = next(
        (
            event
            for event in reversed(history)
            if event.kind == "world_event.accepted"
            and event.payload.get("event_kind") == proposal.event_kind.value
        ),
        None,
    )
    if last_same is not None and proposal.source != "causal-world-response":
        previous = datetime.fromisoformat(str(last_same.payload["starts_at"]))
        cooldown = timedelta(
            hours=6
            if proposal.event_kind is WorldEventKind.WEATHER
            else 48
            if proposal.event_kind is WorldEventKind.AMBIENT
            else 24
        )
        if proposal.starts_at < previous + cooldown:
            return reject("cooldown", "A similar world event happened too recently")

    accepted = effect("world_event.accepted", common)
    if proposal.event_kind is WorldEventKind.WEATHER:
        result = effect(
            "world.weather",
            {
                "text": proposal.description,
                "simulated_at": simulated_at.isoformat(),
                "source": proposal.source,
                "role": proposal.director_id,
            },
        )
    else:
        result = effect("world_event.scheduled", common)
    return WorldEventResolution(True, "accepted", (proposed, accepted, result))
