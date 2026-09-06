"""Activate scheduled public events and create observer-owned perceptions."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.world_events import (
    WorldEventKind,
    WorldEventProposal,
    resolve_world_event,
)

COMMUNITY_RESOURCES = (
    ("seed-swap-table", "Seed swap table", "rowan", "park"),
    ("community-repair-kit", "Community repair kit", "ellis", "workshop"),
    ("shared-tea-service", "Shared tea service", "mara", "cafe"),
    ("community-sketch-basket", "Community sketch basket", "rowan", "park"),
)


def community_resource_events(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    """Register the finite physical resources used by the neighborhood rhythm."""
    if any(event.kind == "world.community_resources_seeded" for event in history):
        return []
    seeded = DomainEvent(
        "world.community_resources_seeded",
        "pathos",
        {"simulated_at": at.isoformat(), "schema_version": 1},
        correlation_id="community-resources-v1",
    )
    existing = project_planning(list(history)).objects
    output = [seeded]
    for object_id, name, owner_id, location_id in COMMUNITY_RESOURCES:
        if object_id in existing:
            continue
        output.append(
            DomainEvent(
                "object.registered",
                "pathos",
                {
                    "object_id": object_id,
                    "name": name,
                    "owner_id": owner_id,
                    "custodian_id": owner_id,
                    "location_id": location_id,
                    "condition": "good",
                    "simulated_at": at.isoformat(),
                    "source": "authored-neighborhood-rhythm-v1",
                },
                causation_id=seeded.event_id,
                correlation_id=seeded.correlation_id,
            )
        )
    return output


def authored_community_schedule(
    history: Sequence[DomainEvent], simulated_at: datetime, actual_revision: int
) -> list[DomainEvent]:
    """Plan one low-stakes weekly neighborhood event with five hours of lead time."""
    day = (simulated_at.date() - datetime(2026, 1, 1).date()).days + 1
    if day < 2 or (day - 2) % 7 != 0 or simulated_at.hour != 8:
        return []
    occurrence = (day - 2) // 7
    event = (
        (
            "seed-swap",
            "Neighbors set out a small table for swapping seeds and cuttings.",
            "park",
            0.25,
            "seed-swap-table",
        ),
        (
            "repair-clinic",
            "The workshop opens a quiet table for neighbors to mend small household things.",
            "workshop",
            0.3,
            "community-repair-kit",
        ),
        (
            "shared-tea",
            "The cafe sets aside a shared pot of tea for an informal neighborhood hour.",
            "cafe",
            0.2,
            "shared-tea-service",
        ),
        (
            "sketch-walk",
            "A small group meets in the square to sketch overlooked corners of the neighborhood.",
            "park",
            0.25,
            "community-sketch-basket",
        ),
    )[occurrence % 4]
    event_id, description, location_id, intensity, resource_id = event
    proposal_id = f"neighborhood-rhythm-{occurrence + 1}-{event_id}"
    if any(item.payload.get("proposal_id") == proposal_id for item in history):
        return []
    resource = project_planning(list(history)).objects.get(resource_id)
    if resource is None or resource.location_id != location_id or resource.condition != "good":
        return [
            DomainEvent(
                "world_event.skipped",
                "pathos",
                {
                    "proposal_id": proposal_id,
                    "resource_id": resource_id,
                    "reason": "Required community resource is unavailable at its event location",
                    "simulated_at": simulated_at.isoformat(),
                },
                correlation_id=proposal_id,
            )
        ]
    resolution = resolve_world_event(
        WorldEventProposal(
            proposal_id=proposal_id,
            director_id="moira",
            event_kind=WorldEventKind.COMMUNITY,
            description=description,
            location_id=location_id,
            starts_at=simulated_at + timedelta(hours=5),
            intensity=intensity,
            expected_revision=actual_revision,
            source="authored-neighborhood-rhythm-v1",
        ),
        history=history,
        known_location_ids={"home", "cafe", "workshop", "park"},
        actual_revision=actual_revision,
        simulated_at=simulated_at,
    )
    output = list(resolution.events)
    if resolution.accepted:
        scheduled = next(
            event for event in resolution.events if event.kind == "world_event.scheduled"
        )
        output.append(
            DomainEvent(
                "world_event.resource_linked",
                "pathos",
                {
                    "proposal_id": proposal_id,
                    "resource_id": resource_id,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=scheduled.event_id,
                correlation_id=proposal_id,
            )
        )
    return output


def due_world_observations(
    history: Sequence[DomainEvent],
    actor_locations: Mapping[str, str],
    simulated_at: datetime,
) -> list[DomainEvent]:
    """Resolve due scheduled events once and reveal them only to co-present actors."""
    occurred_ids = {
        str(event.payload["proposal_id"])
        for event in history
        if event.kind in {"world_event.occurred", "world_event.cancelled"}
    }
    resource_links = {
        str(event.payload["proposal_id"]): str(event.payload["resource_id"])
        for event in history
        if event.kind == "world_event.resource_linked"
    }
    objects = project_planning(list(history)).objects
    output: list[DomainEvent] = []
    for scheduled in history:
        if scheduled.kind != "world_event.scheduled":
            continue
        proposal_id = str(scheduled.payload["proposal_id"])
        starts_at = datetime.fromisoformat(str(scheduled.payload["starts_at"]))
        if proposal_id in occurred_ids or starts_at > simulated_at:
            continue
        location_id = str(scheduled.payload["location_id"])
        resource_id = resource_links.get(proposal_id)
        resource = objects.get(resource_id) if resource_id else None
        if resource_id and (
            resource is None or resource.location_id != location_id or resource.condition != "good"
        ):
            output.append(
                DomainEvent(
                    "world_event.cancelled",
                    "pathos",
                    {
                        "proposal_id": proposal_id,
                        "resource_id": resource_id,
                        "reason": "Required community resource became unavailable",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=scheduled.event_id,
                    correlation_id=scheduled.correlation_id,
                )
            )
            occurred_ids.add(proposal_id)
            continue
        occurred = DomainEvent(
            "world_event.occurred",
            "pathos",
            {
                **dict(scheduled.payload),
                "simulated_at": simulated_at.isoformat(),
                "source_event_id": str(scheduled.event_id),
                "resource_id": resource_id,
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
