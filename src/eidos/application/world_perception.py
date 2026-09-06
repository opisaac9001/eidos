"""Activate scheduled public events and create observer-owned perceptions."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.world_events import (
    WorldEventKind,
    WorldEventProposal,
    resolve_world_event,
)


def authored_community_schedule(
    history: Sequence[DomainEvent], simulated_at: datetime, actual_revision: int
) -> list[DomainEvent]:
    """Seed one calm public event for the initial week without forcing recurring drama."""
    day = (simulated_at.date() - datetime(2026, 1, 1).date()).days + 1
    proposal_id = "willow-seed-swap-day-2"
    if (
        day != 2
        or simulated_at.hour != 8
        or any(event.payload.get("proposal_id") == proposal_id for event in history)
    ):
        return []
    resolution = resolve_world_event(
        WorldEventProposal(
            proposal_id=proposal_id,
            director_id="moira",
            event_kind=WorldEventKind.COMMUNITY,
            description="Neighbors set out a small table for swapping seeds and cuttings.",
            location_id="park",
            starts_at=simulated_at + timedelta(hours=5),
            intensity=0.25,
            expected_revision=actual_revision,
            source="authored-world-v1",
        ),
        history=history,
        known_location_ids={"home", "cafe", "workshop", "park"},
        actual_revision=actual_revision,
        simulated_at=simulated_at,
    )
    return list(resolution.events)


def due_world_observations(
    history: Sequence[DomainEvent],
    actor_locations: Mapping[str, str],
    simulated_at: datetime,
) -> list[DomainEvent]:
    """Resolve due scheduled events once and reveal them only to co-present actors."""
    occurred_ids = {
        str(event.payload["proposal_id"])
        for event in history
        if event.kind == "world_event.occurred"
    }
    output: list[DomainEvent] = []
    for scheduled in history:
        if scheduled.kind != "world_event.scheduled":
            continue
        proposal_id = str(scheduled.payload["proposal_id"])
        starts_at = datetime.fromisoformat(str(scheduled.payload["starts_at"]))
        if proposal_id in occurred_ids or starts_at > simulated_at:
            continue
        location_id = str(scheduled.payload["location_id"])
        occurred = DomainEvent(
            "world_event.occurred",
            "pathos",
            {
                **dict(scheduled.payload),
                "simulated_at": simulated_at.isoformat(),
                "source_event_id": str(scheduled.event_id),
            },
            causation_id=scheduled.event_id,
            correlation_id=scheduled.correlation_id,
        )
        output.append(occurred)
        for actor_id in sorted(actor_locations):
            if actor_locations[actor_id] != location_id:
                continue
            perception = DomainEvent(
                "perception.recorded",
                "pathos",
                {
                    "owner": actor_id,
                    "source_event_id": str(occurred.event_id),
                    "source_kind": "world_event",
                    "text": str(scheduled.payload["description"]),
                    "privacy": "public",
                    "location_id": location_id,
                    "reported": False,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=occurred.event_id,
                correlation_id=scheduled.correlation_id,
            )
            output.append(perception)
            if actor_id == "pathos":
                output.append(
                    DomainEvent(
                        "memory.recorded",
                        "pathos",
                        {
                            "text": str(scheduled.payload["description"]),
                            "owner": "pathos",
                            "category": "world-event",
                            "source": "direct-perception",
                            "source_event_id": str(perception.event_id),
                            "location_id": location_id,
                            "importance": float(scheduled.payload.get("intensity", 0.5)),
                            "confidence": 1.0,
                            "simulated_at": simulated_at.isoformat(),
                        },
                        causation_id=perception.event_id,
                        correlation_id=scheduled.correlation_id,
                    )
                )
        occurred_ids.add(proposal_id)
    return output
