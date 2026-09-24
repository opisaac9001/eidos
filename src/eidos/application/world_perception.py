"""Activate scheduled public events and create observer-owned perceptions."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of, payload_candidates
from eidos.domain.planning import project_planning
from eidos.domain.world_events import (
    WorldEventKind,
    WorldEventProposal,
    resolve_world_event,
)

COMMUNITY_RESOURCES_V1 = (
    ("seed-swap-table", "Seed swap table", "rowan", "park"),
    ("community-repair-kit", "Community repair kit", "ellis", "workshop"),
    ("shared-tea-service", "Shared tea service", "mara", "cafe"),
    ("community-sketch-basket", "Community sketch basket", "rowan", "park"),
)

COMMUNITY_RESOURCES_V2 = (
    ("little-library-crate", "Little library crate", "mara", "cafe"),
    ("bird-count-binoculars", "Bird-count binoculars", "rowan", "park"),
    ("community-mending-basket", "Community mending basket", "ellis", "workshop"),
    ("recipe-card-box", "Neighborhood recipe-card box", "mara", "cafe"),
    ("park-litter-grabbers", "Park litter grabbers", "rowan", "park"),
    ("tool-sharpening-stone", "Shared tool-sharpening stone", "ellis", "workshop"),
    ("reading-hour-books", "Reading-hour book stack", "mara", "cafe"),
    ("leaf-print-press", "Leaf-print press", "rowan", "park"),
    ("community-bicycle-pump", "Community bicycle pump", "ellis", "workshop"),
    ("neighborhood-puzzle-box", "Neighborhood puzzle box", "mara", "cafe"),
    ("park-chalk-box", "Park chalk box", "rowan", "park"),
    ("household-swap-shelf", "Household swap shelf", "ellis", "workshop"),
)

COMMUNITY_RESOURCES = (*COMMUNITY_RESOURCES_V1, *COMMUNITY_RESOURCES_V2)

COMMUNITY_EVENT_PALETTE = (
    (
        "seed-swap",
        "Neighbors set out a small table for swapping seeds and cuttings.",
        "park",
        0.25,
        "seed-swap-table",
        "growing",
        "garden",
    ),
    (
        "repair-clinic",
        "The workshop opens a quiet table for neighbors to mend small household things.",
        "workshop",
        0.30,
        "community-repair-kit",
        "repair",
        "craft",
    ),
    (
        "shared-tea",
        "The cafe sets aside a shared pot of tea for an informal neighborhood hour.",
        "cafe",
        0.20,
        "shared-tea-service",
        "hospitality",
        "conversation",
    ),
    (
        "sketch-walk",
        "A small group meets in the square to sketch overlooked corners of the neighborhood.",
        "park",
        0.25,
        "community-sketch-basket",
        "observation",
        "art",
    ),
    (
        "book-exchange",
        "A crate of well-read books appears at the cafe for an unhurried exchange.",
        "cafe",
        0.18,
        "little-library-crate",
        "reading",
        "learning",
    ),
    (
        "bird-count",
        "Neighbors spend an hour noting the ordinary birds that visit Willow Square.",
        "park",
        0.22,
        "bird-count-binoculars",
        "nature",
        "observation",
    ),
    (
        "mending-circle",
        "The workshop lays out thread and needles for a small clothes-mending circle.",
        "workshop",
        0.24,
        "community-mending-basket",
        "mending",
        "craft",
    ),
    (
        "recipe-swap",
        "People add handwritten recipes to a box on the cafe counter and trade favorites.",
        "cafe",
        0.19,
        "recipe-card-box",
        "cooking",
        "sharing",
    ),
    (
        "square-care-walk",
        "A few neighbors make a slow circuit of the square collecting windblown litter.",
        "park",
        0.23,
        "park-litter-grabbers",
        "care",
        "neighborhood",
    ),
    (
        "tool-care-hour",
        "The workshop hosts a practical hour for cleaning and sharpening shared tools.",
        "workshop",
        0.27,
        "tool-sharpening-stone",
        "maintenance",
        "craft",
    ),
    (
        "quiet-reading",
        "The cafe keeps one table quiet for neighbors who want to read in company.",
        "cafe",
        0.16,
        "reading-hour-books",
        "reading",
        "quiet-company",
    ),
    (
        "leaf-printing",
        "A small press is set out in the square for making prints from fallen leaves.",
        "park",
        0.21,
        "leaf-print-press",
        "season",
        "art",
    ),
    (
        "bicycle-check",
        "The workshop offers a brief check of tires, brakes, and loose bicycle fittings.",
        "workshop",
        0.28,
        "community-bicycle-pump",
        "repair",
        "mobility",
    ),
    (
        "puzzle-table",
        "A half-finished neighborhood puzzle occupies the cafe's shared table for an hour.",
        "cafe",
        0.17,
        "neighborhood-puzzle-box",
        "play",
        "cooperation",
    ),
    (
        "chalk-map",
        "Neighbors draw a temporary chalk map of remembered local details in the square.",
        "park",
        0.20,
        "park-chalk-box",
        "place",
        "storytelling",
    ),
    (
        "household-swap",
        "The workshop opens a shelf for useful household things that need a new home.",
        "workshop",
        0.23,
        "household-swap-shelf",
        "reuse",
        "sharing",
    ),
)


def community_resource_events(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    """Register the finite physical resources used by the neighborhood rhythm."""
    existing = project_planning(history).objects
    missing = [resource for resource in COMMUNITY_RESOURCES if resource[0] not in existing]
    if not missing:
        return []
    seeded = DomainEvent(
        "world.community_resources_seeded",
        "pathos",
        {"simulated_at": at.isoformat(), "schema_version": 2},
        correlation_id="community-resources-v2",
    )
    output = [seeded]
    for object_id, name, owner_id, location_id in missing:
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
                    "source": "authored-neighborhood-rhythm-v2",
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
    event = COMMUNITY_EVENT_PALETTE[occurrence % len(COMMUNITY_EVENT_PALETTE)]
    event_id, description, location_id, intensity, resource_id, theme, opportunity = event
    proposal_id = f"neighborhood-rhythm-{occurrence + 1}-{event_id}"
    if any(
        item.payload.get("proposal_id") == proposal_id
        for item in payload_candidates(history, "proposal_id", proposal_id)
    ):
        return []
    resource = project_planning(history).objects.get(resource_id)
    if (
        resource is None
        or resource.location_id != location_id
        or resource.condition not in {"good", "usable", "repaired"}
        or resource.quantity == 0
    ):
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
            source="authored-neighborhood-rhythm-v2",
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
        output.append(
            DomainEvent(
                "world_event.theme_linked",
                "pathos",
                {
                    "proposal_id": proposal_id,
                    "theme": theme,
                    "opportunity": opportunity,
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
        for event in events_of(history, "world_event.occurred", "world_event.cancelled")
    }
    resource_links = {
        str(event.payload["proposal_id"]): str(event.payload["resource_id"])
        for event in events_of(history, "world_event.resource_linked")
    }
    event_metadata = {
        str(event.payload["proposal_id"]): {
            key: event.payload[key]
            for key in (
                "theme",
                "opportunity",
                "event_type",
                "cause",
                "duration_hours",
                "generated_fiction",
                "participation",
                "stakes",
                "affective_tone",
                "novelty_score",
            )
            if key in event.payload
        }
        for event in events_of(history, "world_event.theme_linked")
    }
    objects = project_planning(history).objects
    output: list[DomainEvent] = []
    for scheduled in events_of(history, "world_event.scheduled"):
        proposal_id = str(scheduled.payload["proposal_id"])
        starts_at = datetime.fromisoformat(str(scheduled.payload["starts_at"]))
        if proposal_id in occurred_ids or starts_at > simulated_at:
            continue
        location_id = str(scheduled.payload["location_id"])
        resource_id = resource_links.get(proposal_id)
        resource = objects.get(resource_id) if resource_id else None
        if resource_id and (
            resource is None
            or resource.location_id != location_id
            or resource.condition not in {"good", "usable", "repaired"}
            or resource.quantity == 0
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
                **event_metadata.get(proposal_id, {}),
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
                    "intensity": scheduled.payload.get("intensity", 0.2),
                    "resource_id": resource_id,
                    **event_metadata.get(proposal_id, {}),
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
                            **event_metadata.get(proposal_id, {}),
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
