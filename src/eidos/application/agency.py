"""Periodically invite and safely schedule Pathos's own novel activities."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from time import perf_counter
from typing import Mapping, Sequence
from uuid import uuid4

from eidos.domain.agency import (
    agency_output_schema,
    parse_agency_candidate,
    resolve_agency_candidate,
)
from eidos.domain.events import DomainEvent
from eidos.domain.mind import CognitiveLayer, project_mind
from eidos.domain.planning import PlanningState
from eidos.domain.proposals import ProposalRejected
from eidos.domain.world_catalog import WorldCatalog
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest


async def autonomous_activity_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    gateway: ModelGateway,
    *,
    planning: PlanningState,
    catalog: WorldCatalog,
    needs: Mapping[str, float],
    emotion: Mapping[str, object],
    values: Mapping[str, float],
    preferences: Sequence[str],
    traits: Mapping[str, float],
    memories: Sequence[str | Mapping[str, object]],
    known_person_ids: frozenset[str] | None = None,
) -> list[DomainEvent]:
    """Ask for one open-ended idea every other day; failure simply leaves free time."""
    day = (simulated_at.date() - datetime(2026, 1, 1).date()).days + 1
    # The authored opening establishes relationships before open-ended agency begins.
    if day < 11 or (day - 11) % 2 != 0 or simulated_at.hour != 10:
        return []
    proposal_id = f"pathos-agency-{simulated_at.date().isoformat()}"
    if any(event.payload.get("proposal_id") == proposal_id for event in history):
        return []
    resources = {
        item.object_id: {
            "name": item.name,
            "location_id": item.location_id,
            "condition": item.condition,
        }
        for item in planning.objects.values()
        if item.condition in {"good", "usable", "repaired"}
        and item.quantity != 0
        and (item.custodian_id == "pathos" or item.owner_id == item.custodian_id == "community")
    }
    people = {
        person.person_id: {"name": person.name, "occupation": person.occupation}
        for person in catalog.people.values()
        if known_person_ids is None or person.person_id in known_person_ids
    }
    places = {
        place.place_id: {
            "name": place.name,
            "description": place.description,
            "opens_hour": place.opens_hour,
            "closes_hour": place.closes_hour,
        }
        for place in catalog.places.values()
    }
    attention = project_mind(history).latest.get(CognitiveLayer.ATTENTION.value)
    context = {
        "time": simulated_at.isoformat(),
        "needs": dict(needs),
        "emotion": dict(emotion),
        "values": dict(values),
        "preferences": list(preferences),
        "traits": dict(traits),
        "recent_memories": list(memories[-8:]),
        "current_attention": (
            {
                "focus_type": attention.focus_type,
                "focus_id": attention.focus_id,
                "focus_text": attention.focus_text,
                "activation": attention.activation,
            }
            if attention is not None
            else None
        ),
        "known_places": places,
        "usable_resources": resources,
        "known_people": people,
        "calendar": [
            {
                "title": entry.title,
                "starts_at": entry.starts_at,
                "ends_at": entry.ends_at,
                "location_id": entry.location_id,
            }
            for entry in planning.calendar.values()
            if entry.status == "scheduled" and entry.actor_id in {None, "pathos"}
        ],
        "permission": (
            "Invent one specific, ordinary activity Pathos might genuinely choose. Let his current "
            "attention matter without treating it as a command. The activity "
            "type is open vocabulary. This is only a proposal: do not say it happened, spend money, "
            "create possessions, or guarantee another person's attendance. Use none when no object "
            "or companion is needed."
        ),
    }
    request = ModelRequest(
        capability="pathos_agency",
        task_version="1",
        temperature=0.9,
        max_output_tokens=320,
        output_schema=agency_output_schema(list(places), list(resources), list(people)),
        messages=(ModelMessage("user", json.dumps(context)),),
    )
    requested = DomainEvent(
        "agency.generation_requested",
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
            raise ProposalRejected("incomplete", "Agency proposal was incomplete")
        candidate = parse_agency_candidate(response.content)
    except (KeyError, OSError, TimeoutError, TypeError, ValueError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
        output.extend(
            (
                DomainEvent(
                    "role.failed",
                    "pathos",
                    {
                        "role": "pathos_agency",
                        "proposal_id": proposal_id,
                        "text": f"Autonomous activity proposal rejected: {error}",
                        "error_code": code,
                        "simulated_at": simulated_at.isoformat(),
                        "trace_id": trace_id,
                    },
                    correlation_id=proposal_id,
                ),
                _trace(
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
                "ok",
                trace_id,
                simulated_at,
                started,
                response.resolved_model,
                response.backend,
                None,
            ),
            DomainEvent(
                "role.completed",
                "pathos",
                {
                    "role": "agency_critic",
                    "status": "ok",
                    "model": "agency-rules-v1",
                    "backend": "rules",
                    "simulated_at": simulated_at.isoformat(),
                    "trace_id": trace_id,
                },
                correlation_id=proposal_id,
            ),
        )
    )
    resolution = resolve_agency_candidate(
        candidate,
        proposal_id=proposal_id,
        state=planning,
        catalog=catalog,
        known_companion_ids=set(people),
        actual_revision=actual_revision + len(output),
        simulated_at=simulated_at,
    )
    output.extend(resolution.events)
    return output


def _trace(
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
            "role": "pathos_agency",
            "status": status,
            "model": model,
            "backend": backend,
            "latency_ms": max(0, round((perf_counter() - started) * 1000)),
            "error_code": error_code,
            "simulated_at": simulated_at.isoformat(),
            "trace_id": trace_id,
        },
    )
