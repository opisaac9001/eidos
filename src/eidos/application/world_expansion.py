"""Invite rare model-proposed additions to the persistent world catalog."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from time import perf_counter
from typing import Sequence
from uuid import uuid4

from eidos.domain.events import DomainEvent
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
) -> list[DomainEvent]:
    """Propose at most one additive entity per weekly expansion budget."""
    day = (simulated_at.date() - datetime(2026, 1, 1).date()).days + 1
    if day < 14 or (day - 14) % 7 != 0 or simulated_at.hour != 17:
        return []
    proposal_id = f"moira-world-expansion-{simulated_at.date().isoformat()}"
    if any(event.payload.get("proposal_id") == proposal_id for event in history):
        return []
    catalog = project_world_catalog(history)
    known_locations = list(catalog.places)
    request = ModelRequest(
        capability="moira_expansion",
        task_version="1",
        temperature=0.9,
        max_output_tokens=420,
        output_schema=world_expansion_output_schema(known_locations),
        messages=(
            ModelMessage(
                "user",
                json.dumps(
                    {
                        "time": simulated_at.isoformat(),
                        "known_places": [
                            {"id": item.place_id, "name": item.name}
                            for item in catalog.places.values()
                        ],
                        "known_people": [item.name for item in catalog.people.values()],
                        "instruction": "Invent one specific person, useful object, or reachable place not already present. Every field is required; fields irrelevant to the chosen kind should contain plausible display defaults.",
                    }
                ),
            ),
        ),
    )
    requested = DomainEvent(
        "world.expansion_generation_requested",
        "pathos",
        {"proposal_id": proposal_id, "simulated_at": simulated_at.isoformat()},
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
        proposal = parse_world_expansion_candidate(
            response.content,
            proposal_id=proposal_id,
            expected_revision=actual_revision + len(output) + 2,
        )
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
