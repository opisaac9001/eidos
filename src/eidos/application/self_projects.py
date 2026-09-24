"""Invite occasional multi-day projects from Pathos's persistent inner context."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from time import perf_counter
from typing import Mapping, Sequence
from uuid import uuid4

from eidos.application.causal_opportunities import fresh_cause, optional_schema
from eidos.application.dream_planning import dream_planning_workspace, dream_project_link_events
from eidos.application.place_discovery import known_world
from eidos.domain.events import DomainEvent
from eidos.domain.folding import payload_candidates
from eidos.domain.mind import CognitiveLayer, project_mind
from eidos.domain.planning import PlanningState
from eidos.domain.proposals import ProposalRejected
from eidos.domain.self_projects import (
    parse_self_project_candidate,
    resolve_self_project,
    self_project_output_schema,
)
from eidos.domain.world_catalog import WorldCatalog
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest


async def autonomous_project_events(
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
    semantic_expectations: Sequence[Mapping[str, object]] = (),
    self_concepts: Sequence[Mapping[str, object]] = (),
    skills: Sequence[Mapping[str, object]] = (),
    habits: Sequence[Mapping[str, object]] = (),
    workspace: Sequence[Mapping[str, object]] = (),
) -> list[DomainEvent]:
    """An idea can invite a project decision, without obliging him to make one."""
    cause = fresh_cause(
        history,
        simulated_at,
        frozenset(
            {
                "thought.recorded",
                "dream.inspiration_considered",
            }
        ),
    )
    if cause is None:
        return []
    if any(
        goal.status == "active" and goal.goal_id.startswith("pathos-project-")
        for goal in planning.goals.values()
    ):
        return []
    proposal_id = f"pathos-project-cause-{cause.event_id}"
    if any(
        event.payload.get("proposal_id") == proposal_id
        for event in payload_candidates(history, "proposal_id", proposal_id)
    ):
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
    catalog = known_world(history, catalog)
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
    planning_workspace = dream_planning_workspace(history, workspace, simulated_at)
    context = {
        "time": simulated_at.isoformat(),
        "needs": dict(needs),
        "emotion": dict(emotion),
        "values": dict(values),
        "preferences": list(preferences),
        "traits": dict(traits),
        "recent_memories": list(memories[-10:]),
        "semantic_expectations": list(semantic_expectations[-8:]),
        "self_concepts": list(self_concepts[-4:]),
        "skills": list(skills[-12:]),
        "habits": list(habits[-6:]),
        "cognitive_workspace": list(planning_workspace[-12:]),
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
            'Return {"no_change": true} unless Pathos deliberately wants to plan a project now. '
            "He chooses whether to commit and the timing of every step. A thought is not a booking. "
            "If chosen, propose one coherent two-to-four-step ordinary project. Let his current attention "
            "matter without treating it as a command. A dream inspiration is a temporary "
            "fiction-sourced possibility, never evidence, action authority, or a promised outcome. "
            "Habits are soft rhythms that may be "
            "continued, varied, or deliberately broken. Skills are demonstrated capability, not "
            "permission or guaranteed success; rusty ability can support a modest refresher. Each step must be "
            "distinct and chronological. Propose only: do not claim progress, spend money, "
            "create possessions, or guarantee success."
        ),
    }
    request = ModelRequest(
        capability="pathos_project",
        task_version="5",
        temperature=0.9,
        max_output_tokens=520,
        output_schema=optional_schema(self_project_output_schema(list(places), list(resources))),
        messages=(ModelMessage("user", json.dumps(context)),),
    )
    requested = DomainEvent(
        "self_project.generation_requested",
        "pathos",
        {
            "proposal_id": proposal_id,
            "source_event_id": str(cause.event_id),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=cause.event_id,
        correlation_id=proposal_id,
    )
    output = [requested]
    trace_id, started, response = str(uuid4()), perf_counter(), None
    try:
        response = await asyncio.wait_for(gateway.generate(request), timeout=50)
        if response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "Project proposal was incomplete")
        if json.loads(response.content) == {"no_change": True}:
            output.append(
                _trace(
                    "ok",
                    trace_id,
                    simulated_at,
                    started,
                    response.resolved_model,
                    response.backend,
                    None,
                    response.prompt_tokens,
                    response.output_tokens,
                )
            )
            output.append(
                DomainEvent(
                    "self_project.left_unplanned",
                    "pathos",
                    {
                        "proposal_id": proposal_id,
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=cause.event_id,
                    correlation_id=proposal_id,
                )
            )
            return output
        candidate = parse_self_project_candidate(response.content)
    except (KeyError, OSError, TimeoutError, TypeError, ValueError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
        output.extend(
            (
                DomainEvent(
                    "role.failed",
                    "pathos",
                    {
                        "role": "pathos_project",
                        "proposal_id": proposal_id,
                        "text": f"Autonomous project proposal rejected: {error}",
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
                    response.prompt_tokens if response else None,
                    response.output_tokens if response else None,
                ),
            )
        )
        return output
    output.append(
        _trace(
            "ok",
            trace_id,
            simulated_at,
            started,
            response.resolved_model,
            response.backend,
            None,
            response.prompt_tokens,
            response.output_tokens,
        )
    )
    resolution = resolve_self_project(
        candidate,
        proposal_id=proposal_id,
        state=planning,
        catalog=catalog,
        actual_revision=actual_revision + len(output),
        simulated_at=simulated_at,
    )
    output.extend(resolution.events)
    output.extend(
        dream_project_link_events(history, planning_workspace, resolution.events, simulated_at)
    )
    return output


def _trace(
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
            "role": "pathos_project",
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
