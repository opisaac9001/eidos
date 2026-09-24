"""Invite rare model-proposed additions to the persistent world catalog."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime, timedelta
from time import perf_counter
from typing import Sequence
from uuid import uuid4

from eidos.domain.events import DomainEvent
from eidos.domain.folding import payload_candidates
from eidos.domain.proposals import ProposalRejected
from eidos.domain.world_catalog import (
    parse_world_expansion_candidate,
    project_world_catalog,
    resolve_world_expansion,
    world_expansion_output_schema,
)
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest


async def expanding_world_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    gateway: ModelGateway,
    pathos_location_id: str | None = None,
) -> list[DomainEvent]:
    """Consider one discovery per fresh public arrival, never because a day is due."""
    if simulated_at.utcoffset() is None:
        raise ValueError("World expansion time must be timezone-aware")
    if pathos_location_id is None or pathos_location_id == "home":
        return []
    arrival = next((event for event in reversed(history) if event.kind == "pathos.moved"), None)
    if arrival is None or arrival.payload.get("location_id") != pathos_location_id:
        return []
    try:
        arrived_at = datetime.fromisoformat(str(arrival.payload.get("simulated_at")))
        if arrived_at.utcoffset() is None or not timedelta(
            0
        ) <= simulated_at - arrived_at <= timedelta(hours=1):
            return []
    except ValueError:
        return []
    proposal_id = f"moira-world-expansion-arrival-{arrival.event_id}"
    if any(
        event.payload.get("proposal_id") == proposal_id
        for event in payload_candidates(history, "proposal_id", proposal_id)
    ):
        return []
    catalog = project_world_catalog(history)
    if pathos_location_id not in catalog.places:
        return []
    known_locations = list(catalog.places)
    request = ModelRequest(
        capability="moira_expansion",
        task_version="2",
        temperature=0.9,
        max_output_tokens=420,
        output_schema={
            "anyOf": [
                world_expansion_output_schema(known_locations),
                {
                    "type": "object",
                    "properties": {"no_change": {"const": True}},
                    "required": ["no_change"],
                    "additionalProperties": False,
                },
            ]
        },
        messages=(
            ModelMessage(
                "user",
                json.dumps(
                    {
                        "time": simulated_at.isoformat(),
                        "pathos_location_id": pathos_location_id,
                        "cause": {"event_id": str(arrival.event_id), "kind": arrival.kind},
                        "known_places": [
                            {"id": item.place_id, "name": item.name}
                            for item in catalog.places.values()
                        ],
                        "known_people": [item.name for item in catalog.people.values()],
                        "instruction": 'Pathos has arrived here. Usually nothing new needs to be invented: return {"no_change": true} for an ordinary arrival. Only if this situation naturally supports a discovery, propose one person he encounters, an object he notices, or a place he learns about here. Do not create a tour, automatic friendship, past memory or remote encounter. A new place must connect to his current location. For an entity, every schema field is required.',
                    }
                ),
            ),
        ),
    )
    requested = DomainEvent(
        "world.expansion_generation_requested",
        "pathos",
        {
            "proposal_id": proposal_id,
            "source_event_id": str(arrival.event_id),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=arrival.event_id,
        correlation_id=proposal_id,
    )
    output = [requested]
    trace_id = str(uuid4())
    started = perf_counter()
    response = None
    try:
        response = await asyncio.wait_for(gateway.generate(request), timeout=50)
        if response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "World expansion proposal was incomplete")
        if json.loads(response.content) == {"no_change": True}:
            output.append(
                _trace(
                    "moira_expansion",
                    "ok",
                    trace_id,
                    simulated_at,
                    started,
                    response.resolved_model,
                    response.backend,
                    None,
                )
            )
            output.append(
                DomainEvent(
                    "world.expansion_kept_ordinary",
                    "pathos",
                    {"proposal_id": proposal_id, "simulated_at": simulated_at.isoformat()},
                    causation_id=arrival.event_id,
                    correlation_id=proposal_id,
                )
            )
            return output
        proposal = parse_world_expansion_candidate(
            response.content,
            proposal_id=proposal_id,
            expected_revision=actual_revision + len(output) + 2,
        )
        if proposal.entity_kind.value in {"place", "object"}:
            proposal = replace(proposal, location_id=pathos_location_id)
        if proposal.entity_kind.value == "person" and pathos_location_id is not None:
            if pathos_location_id == "home":
                raise ProposalRejected(
                    "private_location",
                    "A new resident cannot materialize inside Pathos's private home",
                )
            proposal = replace(proposal, location_id=pathos_location_id)
    except (OSError, TimeoutError, TypeError, ValueError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
        output.extend(
            (
                DomainEvent(
                    "role.failed",
                    "pathos",
                    {
                        "role": "moira_expansion",
                        "proposal_id": proposal_id,
                        "text": f"World expansion rejected: {error}",
                        "error_code": code,
                        "simulated_at": simulated_at.isoformat(),
                        "trace_id": trace_id,
                    },
                    correlation_id=proposal_id,
                ),
                _trace(
                    "moira_expansion",
                    "failed",
                    trace_id,
                    simulated_at,
                    started,
                    response.resolved_model if response else getattr(gateway, "model", "unknown"),
                    response.backend if response else "unknown",
                    code,
                ),
            )
        )
        return output
    output.extend(
        (
            _trace(
                "moira_expansion",
                "ok",
                trace_id,
                simulated_at,
                started,
                response.resolved_model,
                response.backend,
                None,
            ),
            _trace(
                "critic",
                "ok",
                trace_id,
                simulated_at,
                started,
                "world-catalog-rules-v1",
                "rules",
                None,
            ),
        )
    )
    resolution = resolve_world_expansion(
        proposal,
        catalog=catalog,
        actual_revision=actual_revision + len(output),
        simulated_at=simulated_at.isoformat(),
    )
    output.extend(resolution.events)
    if resolution.accepted and proposal.entity_kind.value == "person":
        registered = next(
            event for event in resolution.events if event.kind == "world.person_registered"
        )
        if pathos_location_id is not None:
            materialized = DomainEvent(
                "person.materialized_from_ambient_population",
                "pathos",
                {
                    "person_id": proposal.entity_id,
                    "registration_event_id": str(registered.event_id),
                    "population_window_id": (
                        f"{simulated_at.date().isoformat()}:{simulated_at.hour}:"
                        f"{pathos_location_id}"
                    ),
                    "location_id": pathos_location_id,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=registered.event_id,
                correlation_id=proposal.proposal_id,
            )
            encounter = DomainEvent(
                "npc.encountered",
                "pathos",
                {
                    "person_id": proposal.entity_id,
                    "text": f"Met {proposal.name} for the first time.",
                    "simulated_at": simulated_at.isoformat(),
                    "location_id": pathos_location_id,
                    "source": "world-encounter",
                    "role": "moira_expansion",
                },
                causation_id=materialized.event_id,
                correlation_id=proposal.proposal_id,
            )
            output.extend(
                (
                    materialized,
                    encounter,
                    DomainEvent(
                        "memory.recorded",
                        "pathos",
                        {
                            "text": f"I met {proposal.name} for the first time.",
                            "simulated_at": simulated_at.isoformat(),
                            "source": "direct-encounter",
                            "source_event_id": str(encounter.event_id),
                            "category": "relationship",
                            "location_id": pathos_location_id,
                            "person_id": proposal.entity_id,
                            "owner": "pathos",
                            "importance": 0.62,
                        },
                        causation_id=encounter.event_id,
                        correlation_id=proposal.proposal_id,
                    ),
                )
            )
    return output


def _trace(
    role: str,
    status: str,
    trace_id: str,
    simulated_at: datetime,
    started: float,
    model: str,
    backend: str,
    error_code: str | None,
) -> DomainEvent:
    return DomainEvent(
        "role.completed",
        "pathos",
        {
            "role": role,
            "simulated_at": simulated_at.isoformat(),
            "status": status,
            "trace_id": trace_id,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "model": model,
            "backend": backend,
            "error_code": error_code,
        },
    )
