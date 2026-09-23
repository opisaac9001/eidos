"""Model-proposed, actor-private plans for independently living NPCs."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from time import perf_counter
from typing import Mapping, Sequence
from uuid import uuid4

from eidos.application.causal_opportunities import optional_schema
from eidos.domain.events import DomainEvent
from eidos.domain.npc_agency import (
    npc_agency_output_schema,
    parse_npc_agency_candidate,
)
from eidos.domain.npcs import project_npcs
from eidos.domain.proposals import ProposalRejected
from eidos.domain.relationships import Relationship
from eidos.domain.world import location_allows_interval
from eidos.domain.world_catalog import WorldCatalog
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest


async def autonomous_npc_plan_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    gateway: ModelGateway,
    catalog: WorldCatalog,
    shared_relationships: Mapping[str, Relationship] | None = None,
    allowed_actor_ids: frozenset[str] | None = None,
) -> list[DomainEvent]:
    """Consider a changed private need, not a daily appointment with the model."""
    if simulated_at.utcoffset() is None:
        raise ValueError("NPC agency time must be timezone-aware")
    state = project_npcs(history, simulated_at)
    consumed = {
        str(event.payload["evidence_need_event_id"])
        for event in history
        if event.kind
        in {"npc.plan_created", "npc.agency_rejected", "npc.agency_generation_requested"}
        and isinstance(event.payload.get("evidence_need_event_id"), str)
    }
    output: list[DomainEvent] = []
    for actor_id, person in state.people.items():
        if allowed_actor_ids is not None and actor_id not in allowed_actor_ids:
            continue
        evidence = next(
            (
                event
                for event in reversed(history)
                if event.kind == "npc.needs_changed"
                and event.payload.get("actor_id") == actor_id
                and event.payload.get("owner") == actor_id
                and str(event.event_id) not in consumed
            ),
            None,
        )
        if evidence is None or person.plan_status == "active":
            continue
        try:
            evidence_at = datetime.fromisoformat(str(evidence.payload.get("simulated_at")))
        except ValueError:
            continue
        if evidence_at.utcoffset() is None or not timedelta(
            0
        ) <= simulated_at - evidence_at <= timedelta(hours=6):
            continue
        needs = {
            "energy": person.energy,
            "connection": person.connection,
            "purpose": person.purpose,
        }
        eligible = {name: level for name, level in needs.items() if level < 0.58}
        if not eligible:
            continue
        familiarity = (
            shared_relationships.get(actor_id, Relationship(actor_id)).familiarity
            if shared_relationships is not None
            else 0.0
        )
        scores = {
            name: level
            - (0.12 * familiarity if name == "connection" else 0.0)
            - (0.1 if name == "energy" and level <= 0.25 else 0.0)
            for name, level in eligible.items()
        }
        need = min(eligible, key=lambda name: (scores[name], name))
        pressure_band = f"{need}:{int(eligible[need] * 5)}"
        previous = next(
            (
                event
                for event in reversed(history)
                if event.kind == "npc.agency_generation_requested"
                and event.payload.get("actor_id") == actor_id
            ),
            None,
        )
        if (
            previous is not None
            and previous.payload.get("pressure_band") == pressure_band
            and person.plan_status != "interrupted"
        ):
            continue
        proposal_id = f"npc-agency-{actor_id}-{evidence.event_id}"
        trace_id = str(uuid4())
        requested = DomainEvent(
            "npc.agency_generation_requested",
            "pathos",
            {
                "actor_id": actor_id,
                "proposal_id": proposal_id,
                "evidence_need_event_id": str(evidence.event_id),
                "pressure_band": pressure_band,
                "owner": actor_id,
                "visibility": "private",
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=evidence.event_id,
            correlation_id=proposal_id,
        )
        output.append(requested)
        owned_context = _owned_context(history, actor_id)
        actor = catalog.people.get(actor_id)
        context = {
            "time": simulated_at.isoformat(),
            "actor": {
                "id": actor_id,
                "name": actor.name if actor else actor_id,
                "occupation": actor.occupation if actor else "neighbor",
                "usual_location_id": person.usual_location_id,
            },
            "needs": needs,
            "selected_need": need,
            "known_places": {
                place.place_id: {
                    "name": place.name,
                    "description": place.description,
                    "opens_hour": place.opens_hour,
                    "closes_hour": place.closes_hour,
                }
                for place in catalog.places.values()
            },
            "private_context": owned_context,
            "permission": (
                'Return {"no_change": true} to continue, defer, or leave the need unacted on. '
                "Only propose a private plan if this resident chooses it, including its timing. Use only their context. "
                "Do not claim it happened, create property, spend money, or control another actor."
            ),
        }
        request = ModelRequest(
            capability="npc_agency",
            task_version="2",
            temperature=0.9,
            max_output_tokens=280,
            output_schema=optional_schema(npc_agency_output_schema(list(catalog.places))),
            messages=(ModelMessage("user", json.dumps(context)),),
        )
        started = perf_counter()
        response = None
        try:
            response = await asyncio.wait_for(gateway.generate(request), timeout=50)
            if response.finish_reason != "stop":
                raise ProposalRejected("incomplete", "NPC agency proposal was incomplete")
            if json.loads(response.content) == {"no_change": True}:
                output.extend(
                    [
                        _trace(
                            actor_id,
                            "ok",
                            trace_id,
                            simulated_at,
                            started,
                            response.resolved_model,
                            response.backend,
                            None,
                            response.prompt_tokens,
                            response.output_tokens,
                        ),
                        DomainEvent(
                            "npc.idea_left_unplanned",
                            "pathos",
                            {
                                "actor_id": actor_id,
                                "owner": actor_id,
                                "visibility": "private",
                                "proposal_id": proposal_id,
                                "simulated_at": simulated_at.isoformat(),
                            },
                            causation_id=requested.event_id,
                            correlation_id=proposal_id,
                        ),
                    ]
                )
                continue
            candidate = parse_npc_agency_candidate(response.content)
            if candidate.location_id not in catalog.places:
                raise ProposalRejected("unknown_location", "The proposed place does not exist")
            starts_at = (simulated_at + timedelta(days=candidate.day_offset)).replace(
                hour=candidate.scheduled_hour, minute=0, second=0, microsecond=0
            )
            ends_at = starts_at + timedelta(hours=1)
            if starts_at < simulated_at:
                raise ProposalRejected("past_start", "A chosen NPC plan cannot start in the past")
            if not location_allows_interval(
                candidate.location_id, starts_at, ends_at, catalog.opening_hours
            ):
                raise ProposalRejected("place_closed", "The proposed place is closed")
        except (KeyError, OSError, TimeoutError, TypeError, ValueError) as error:
            code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
            output.extend(
                (
                    DomainEvent(
                        "npc.agency_rejected",
                        "pathos",
                        {
                            "actor_id": actor_id,
                            "proposal_id": proposal_id,
                            "evidence_need_event_id": str(evidence.event_id),
                            "code": code,
                            "owner": actor_id,
                            "visibility": "private",
                            "simulated_at": simulated_at.isoformat(),
                        },
                        causation_id=requested.event_id,
                        correlation_id=proposal_id,
                    ),
                    _trace(
                        actor_id,
                        "failed",
                        trace_id,
                        simulated_at,
                        started,
                        response.resolved_model
                        if response
                        else getattr(gateway, "model", "unknown"),
                        response.backend if response else "unknown",
                        code,
                        response.prompt_tokens if response else None,
                        response.output_tokens if response else None,
                    ),
                )
            )
            consumed.add(str(evidence.event_id))
            continue
        priority = DomainEvent(
            "npc.priority_evaluated",
            "pathos",
            {
                "actor_id": actor_id,
                **{f"{name}_level": level for name, level in needs.items()},
                **{f"{name}_priority": scores.get(name) for name in needs},
                "shared_familiarity": familiarity,
                "selected_need": need,
                "selected_level": eligible[need],
                "replacement": False,
                "evidence_need_event_id": str(evidence.event_id),
                "owner": actor_id,
                "visibility": "private",
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=evidence.event_id,
            correlation_id=proposal_id,
        )
        accepted = DomainEvent(
            "npc.agency_accepted",
            "pathos",
            {
                "actor_id": actor_id,
                "proposal_id": proposal_id,
                "activity_type": candidate.activity_type,
                "owner": actor_id,
                "visibility": "private",
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=requested.event_id,
            correlation_id=proposal_id,
        )
        goal_id = f"{proposal_id}-goal"
        goal = DomainEvent(
            "npc.goal_formed",
            "pathos",
            {
                "actor_id": actor_id,
                "goal_id": goal_id,
                "title": candidate.title,
                "motivation": candidate.motivation,
                "motivation_need": need,
                "evidence_need_event_id": str(evidence.event_id),
                "owner": actor_id,
                "visibility": "private",
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=accepted.event_id,
            correlation_id=proposal_id,
        )
        plan = DomainEvent(
            "npc.plan_created",
            "pathos",
            {
                "actor_id": actor_id,
                "plan_id": f"{proposal_id}-plan",
                "title": candidate.title,
                "action": candidate.action,
                "activity_type": candidate.activity_type,
                "location_id": candidate.location_id,
                "scheduled_for": starts_at.isoformat(),
                "due_at": (starts_at + timedelta(hours=6)).isoformat(),
                "motivation": candidate.motivation,
                "motivation_need": need,
                "goal_id": goal_id,
                "evidence_need_event_id": str(evidence.event_id),
                "owner": actor_id,
                "visibility": "private",
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=goal.event_id,
            correlation_id=proposal_id,
        )
        output.extend(
            (
                _trace(
                    actor_id,
                    "ok",
                    trace_id,
                    simulated_at,
                    started,
                    response.resolved_model,
                    response.backend,
                    None,
                    response.prompt_tokens,
                    response.output_tokens,
                ),
                priority,
                accepted,
                goal,
                plan,
            )
        )
        state = state.apply(goal).apply(plan)
        consumed.add(str(evidence.event_id))
    return output


def _owned_context(history: Sequence[DomainEvent], actor_id: str) -> list[dict[str, object]]:
    return [
        {
            "kind": event.kind,
            "text": event.payload.get("text") or event.payload.get("activity"),
            "location_id": event.payload.get("location_id"),
            "simulated_at": event.payload.get("simulated_at"),
        }
        for event in history
        if event.payload.get("owner") == actor_id
        and event.kind in {"perception.recorded", "npc.activity_recorded", "npc.biography_seeded"}
    ][-8:]


def _latest_actor_times(history: Sequence[DomainEvent], kind: str) -> dict[str, datetime]:
    result: dict[str, datetime] = {}
    for event in history:
        if event.kind != kind:
            continue
        actor_id, raw = event.payload.get("actor_id"), event.payload.get("simulated_at")
        if not isinstance(actor_id, str) or not isinstance(raw, str):
            continue
        try:
            value = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if value.utcoffset() is not None:
            result[actor_id] = max(result.get(actor_id, value), value)
    return result


def _within(previous: datetime | None, now: datetime, duration: timedelta) -> bool:
    return previous is not None and now - previous < duration


def _trace(
    actor_id: str,
    status: str,
    trace_id: str,
    simulated_at: datetime,
    started: float,
    model: str,
    backend: str,
    error_code: str | None,
    prompt_tokens: int | None,
    output_tokens: int | None,
) -> DomainEvent:
    return DomainEvent(
        "role.completed",
        "pathos",
        {
            "role": "npc_agency",
            "actor_id": actor_id,
            "status": status,
            "model": model,
            "backend": backend,
            "latency_ms": max(0, round((perf_counter() - started) * 1000)),
            "error_code": error_code,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "simulated_at": simulated_at.isoformat(),
            "trace_id": trace_id,
        },
    )
