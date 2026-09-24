"""Generate bounded private histories for residents invented during simulation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import datetime, timedelta
from time import perf_counter
from uuid import uuid4

from eidos.domain.character_generation import (
    character_history_output_schema,
    parse_character_history_candidate,
)
from eidos.domain.character_history import project_character_history
from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected
from eidos.domain.world_catalog import project_world_catalog
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest, ModelResponse


async def generated_character_history_events(
    history: Sequence[DomainEvent], simulated_at: datetime, gateway: ModelGateway
) -> list[DomainEvent]:
    """Attempt one due invented resident, with a bounded restart-safe retry policy."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Character generation time must be timezone-aware")
    catalog = project_world_catalog(history)
    facts = project_character_history(history).facts
    registrations = [
        event
        for event in history
        if event.kind == "world.person_registered"
        and isinstance(event.payload.get("proposal_id"), str)
        and str(event.payload["proposal_id"]).startswith(
            ("moira-world-expansion-", "townsfolk-promotion-")
        )
    ]
    for registration in registrations:
        person_id = str(registration.payload["entity_id"])
        if any(fact.person_id == person_id for fact in facts.values()):
            continue
        attempts = [
            event
            for event in history
            if event.kind == "npc.biography_generation_requested"
            and event.payload.get("person_id") == person_id
        ]
        if len(attempts) >= 3:
            continue
        latest = attempts[-1] if attempts else None
        if latest is not None:
            attempted_at = datetime.fromisoformat(str(latest.payload["simulated_at"]))
            if simulated_at < attempted_at + timedelta(hours=24):
                continue
        person = catalog.people.get(person_id)
        if person is None:
            continue
        attempt = len(attempts) + 1
        generation_id = f"resident-history-{person_id}-{attempt}"
        requested = DomainEvent(
            "npc.biography_generation_requested",
            "pathos",
            {
                "generation_id": generation_id,
                "person_id": person_id,
                "attempt": attempt,
                "owner": person_id,
                "visibility": "private",
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=registration.event_id,
            correlation_id=generation_id,
        )
        context = {
            "time": simulated_at.isoformat(),
            "resident": {
                "id": person.person_id,
                "name": person.name,
                "description": person.description,
                "occupation": person.occupation,
                "home_location_id": person.home_location_id,
            },
            "permission": (
                "Invent three distinct, ordinary first-person facts from this resident's past. "
                "They may be imaginative, but must not involve any known resident, assert a present "
                "world event, or introduce crimes, abuse, diagnoses, property, or obligations. The "
                "first may be easy to share, the second personal, and the third deeply held."
            ),
        }
        request = ModelRequest(
            capability="npc_backstory",
            task_version="1",
            temperature=0.95,
            max_output_tokens=420,
            output_schema=character_history_output_schema(),
            messages=(ModelMessage("user", json.dumps(context)),),
        )
        output = [requested]
        response = None
        trace_id = str(uuid4())
        started = perf_counter()
        try:
            response = await asyncio.wait_for(gateway.generate(request), timeout=50)
            if response.finish_reason != "stop":
                raise ProposalRejected("incomplete", "Resident history was incomplete")
            candidate = parse_character_history_candidate(
                response.content,
                known_people=[item.name for item in catalog.people.values()],
            )
        except (OSError, TimeoutError, TypeError, ValueError) as error:
            code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
            output.extend(
                (
                    DomainEvent(
                        "npc.biography_generation_failed",
                        "pathos",
                        {
                            "generation_id": generation_id,
                            "person_id": person_id,
                            "attempt": attempt,
                            "error_code": code,
                            "owner": person_id,
                            "visibility": "private",
                            "simulated_at": simulated_at.isoformat(),
                        },
                        causation_id=requested.event_id,
                        correlation_id=generation_id,
                    ),
                    _trace("failed", trace_id, simulated_at, started, response, gateway, code),
                )
            )
            return output
        output.append(_trace("ok", trace_id, simulated_at, started, response, gateway, None))
        for index, fact in enumerate(candidate, 1):
            output.append(
                DomainEvent(
                    "npc.biography_seeded",
                    "pathos",
                    {
                        "fact_id": f"{person_id}-generated-{index}",
                        "person_id": person_id,
                        "topic": fact.topic,
                        "text": fact.text,
                        "reveal_after_familiarity": fact.reveal_after_familiarity,
                        "source": "model-private-fiction",
                        "generation_id": generation_id,
                        "owner": person_id,
                        "visibility": "private",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=requested.event_id,
                    correlation_id=generation_id,
                )
            )
        return output
    return []


def _trace(
    status: str,
    trace_id: str,
    simulated_at: datetime,
    started: float,
    response: ModelResponse | None,
    gateway: ModelGateway,
    error_code: str | None,
) -> DomainEvent:
    return DomainEvent(
        "role.completed",
        "pathos",
        {
            "role": "npc_backstory",
            "status": status,
            "trace_id": trace_id,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "model": response.resolved_model if response else getattr(gateway, "model", "unknown"),
            "backend": response.backend if response else "unknown",
            "error_code": error_code,
            "simulated_at": simulated_at.isoformat(),
        },
    )
