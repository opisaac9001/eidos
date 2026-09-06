"""Invite open-ended fictional world proposals without granting prose state authority."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from time import perf_counter
from typing import Mapping, Sequence
from uuid import uuid4

from eidos.domain.ambient import (
    ambient_output_schema,
    parse_ambient_candidate,
    validate_ambient_candidate,
)
from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected
from eidos.domain.world_events import WorldEventKind, WorldEventProposal, resolve_world_event
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest


async def improvised_world_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    gateway: ModelGateway,
    *,
    season: str,
    weather: str,
    known_locations: Mapping[str, str] | None = None,
    known_resources: Mapping[str, str] | None = None,
    external_signals: Mapping[str, str] | None = None,
) -> list[DomainEvent]:
    """Ask Moira periodically; rejection or failure means an ordinary quiet interval."""
    if simulated_at.utcoffset() is None:
        raise ValueError("World improvisation time must be timezone-aware")
    day = (simulated_at.date() - datetime(2026, 1, 1).date()).days + 1
    if day < 7 or (day - 7) % 3 != 0 or simulated_at.hour != 18:
        return []
    proposal_id = f"moira-open-world-{simulated_at.date().isoformat()}"
    if any(event.payload.get("proposal_id") == proposal_id for event in history):
        return []
    recent = [
        str(event.payload.get("description", ""))
        for event in history
        if event.kind == "world_event.accepted"
    ][-12:]
    locations = dict(
        known_locations
        or {
            "home": "The apartment",
            "cafe": "Juniper Café",
            "workshop": "The workshop",
            "park": "Willow Square",
        }
    )
    resources = dict(
        {
            "seed-swap-table": "park",
            "community-repair-kit": "workshop",
            "shared-tea-service": "cafe",
            "community-sketch-basket": "park",
        }
        if known_resources is None
        else known_resources
    )
    if not resources:
        return []
    signals = dict(external_signals or {})
    request = ModelRequest(
        capability="moira_event",
        task_version="3",
        temperature=0.85,
        max_output_tokens=300,
        output_schema=ambient_output_schema(tuple(locations), tuple(resources), tuple(signals)),
        messages=(
            ModelMessage(
                "user",
                json.dumps(
                    {
                        "time": simulated_at.isoformat(),
                        "season": season,
                        "weather": weather,
                        "known_locations": locations,
                        "known_resources": resources,
                        "recent_events": recent,
                        "external_signals": signals,
                        "permission": (
                            "Invent new fictional material; do not claim it already happened. "
                            "External signals are attributed inspiration only, not reports about "
                            "the fictional town. Cite one signal ID if used, otherwise use none."
                        ),
                    }
                ),
            ),
        ),
    )
    trace_id = str(uuid4())
    started = perf_counter()
    response = None
    output: list[DomainEvent] = [
        DomainEvent(
            "world_event.generation_requested",
            "pathos",
            {
                "proposal_id": proposal_id,
                "director_id": "moira",
                "simulated_at": simulated_at.isoformat(),
            },
            correlation_id=proposal_id,
        )
    ]
    try:
        response = await asyncio.wait_for(gateway.generate(request), timeout=50)
        if response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "Moira's proposal was incomplete")
        candidate = parse_ambient_candidate(response.content)
        novelty_score = validate_ambient_candidate(
            candidate,
            known_locations=set(locations),
            known_resources=resources,
            known_signal_ids=set(signals),
            history=history,
        )
    except (KeyError, OSError, TimeoutError, TypeError, ValueError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
        output.extend(
            (
                DomainEvent(
                    "role.failed",
                    "pathos",
                    {
                        "role": "moira_event",
                        "proposal_id": proposal_id,
                        "text": f"Open-world proposal rejected: {error}",
                        "error_code": code,
                        "simulated_at": simulated_at.isoformat(),
                        "trace_id": trace_id,
                    },
                ),
                _trace_event(
                    "moira_event",
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
        if response is not None:
            output.append(
                _trace_event(
                    "critic",
                    "rejected",
                    trace_id,
                    simulated_at,
                    started,
                    "schema-rules-v3",
                    "rules",
                    code,
                )
            )
        return output
    output.extend(
        (
            _trace_event(
                "moira_event",
                "ok",
                trace_id,
                simulated_at,
                started,
                response.resolved_model,
                response.backend,
                None,
            ),
            _trace_event(
                "critic",
                "ok",
                trace_id,
                simulated_at,
                started,
                "schema-rules-v3",
                "rules",
                None,
            ),
        )
    )
    resolution = resolve_world_event(
        WorldEventProposal(
            proposal_id=proposal_id,
            director_id="moira",
            event_kind=WorldEventKind.AMBIENT,
            description=candidate.description,
            location_id=candidate.location_id,
            starts_at=simulated_at + timedelta(hours=candidate.starts_in_hours),
            intensity=candidate.intensity,
            expected_revision=actual_revision + len(output),
            source="model-fiction-proposal",
        ),
        history=[*history, *output],
        known_location_ids=set(locations),
        actual_revision=actual_revision + len(output),
        simulated_at=simulated_at,
    )
    output.extend(resolution.events)
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
                    "resource_id": candidate.resource_id,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=scheduled.event_id,
                correlation_id=proposal_id,
            )
        )
        if candidate.inspiration_signal_id != "none":
            output.append(
                DomainEvent(
                    "world_event.signal_linked",
                    "pathos",
                    {
                        "proposal_id": proposal_id,
                        "signal_id": candidate.inspiration_signal_id,
                        "signal_text": signals[candidate.inspiration_signal_id],
                        "world_fact": False,
                        "action_authority": False,
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
                    "event_type": candidate.event_type,
                    "theme": candidate.theme,
                    "opportunity": candidate.opportunity,
                    "participation": candidate.participation,
                    "stakes": candidate.stakes,
                    "cause": candidate.cause,
                    "duration_hours": candidate.duration_hours,
                    "novelty_score": novelty_score,
                    "generated_fiction": True,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=scheduled.event_id,
                correlation_id=proposal_id,
            )
        )
    return output


def _trace_event(
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
