"""Periodically invite and safely schedule Pathos's own novel activities."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from time import perf_counter
from typing import Mapping, Sequence
from uuid import uuid4

from eidos.application.activity_execution import execution_context
from eidos.application.causal_opportunities import fresh_cause
from eidos.application.dream_planning import dream_plan_link_events, dream_planning_workspace
from eidos.application.opportunities import available_opportunities
from eidos.application.preparation import preparation_context
from eidos.application.time_budget import personal_time_budget
from eidos.application.volition import attended_impulses, impulse_attention_event
from eidos.domain.agency import (
    agency_output_schema,
    parse_agency_candidate,
    resolve_agency_candidate,
)
from eidos.domain.events import DomainEvent
from eidos.domain.household import project_household
from eidos.domain.mind import CognitiveLayer, project_mind
from eidos.domain.planning import PlanningState
from eidos.domain.proposals import ProposalRejected
from eidos.domain.selfhood import STARTING_VALUES, developed_values, project_selfhood
from eidos.domain.travel import route_duration
from eidos.domain.world_catalog import WorldCatalog
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest

_MEAL_ACTIVITY_TYPES = frozenset(
    {
        "breakfast",
        "cook_food",
        "eat_meal",
        "evening_meal",
        "lunch",
        "make_breakfast",
        "make_dinner",
        "make_lunch",
        "meal",
        "meal_preparation",
        "prepare_and_eat_meal",
        "prepare_food",
        "snack",
    }
)


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
    semantic_expectations: Sequence[Mapping[str, object]] = (),
    self_concepts: Sequence[Mapping[str, object]] = (),
    skills: Sequence[Mapping[str, object]] = (),
    habits: Sequence[Mapping[str, object]] = (),
    workspace: Sequence[Mapping[str, object]] = (),
    known_person_ids: frozenset[str] | None = None,
    current_location_id: str | None = None,
) -> list[DomainEvent]:
    """A fresh thought or experience invites a choice, never requires a plan."""
    cause = fresh_cause(
        history,
        simulated_at,
        frozenset(
            {
                "thought.recorded",
                "perception.recorded",
                "activity.completed",
                "intention.adopted",
                "dream.inspiration_considered",
                "opportunity.noticed",
            }
        ),
    )
    if cause is None:
        return []
    proposal_id = f"pathos-agency-cause-{cause.event_id}"
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
    planning_workspace = dream_planning_workspace(history, workspace, simulated_at)
    if cause.kind in {"thought.recorded", "perception.recorded"} and not any(
        item.get("source_event_id") == str(cause.event_id) for item in planning_workspace
    ):
        cause_text = cause.payload.get("text")
        if isinstance(cause_text, str) and cause_text.strip():
            raw_importance = cause.payload.get("importance", 0.6)
            salience = (
                float(raw_importance)
                if isinstance(raw_importance, (int, float)) and not isinstance(raw_importance, bool)
                else 0.6
            )
            planning_workspace.append(
                {
                    "source_event_id": str(cause.event_id),
                    "from_faculty": "present_experience",
                    "kind": "present_thought"
                    if cause.kind == "thought.recorded"
                    else "present_perception",
                    "content": cause_text.strip()[:220],
                    "salience": max(0.0, min(1.0, salience)),
                    "epistemic_status": "inner_monologue"
                    if cause.kind == "thought.recorded"
                    else "perceived_experience",
                    "action_authority": False,
                }
            )
    planning_question = next(
        (
            item
            for item in planning_workspace
            if item.get("epistemic_status") == "planning_question"
            and item.get("action_authority") is False
        ),
        None,
    )
    recent_activity_patterns = _recent_activity_patterns(history, simulated_at)
    time_budget = personal_time_budget(
        planning, catalog, simulated_at, current_location_id or "home"
    )
    opportunities = available_opportunities(history, simulated_at)
    preparation = preparation_context(
        history, location_id=current_location_id, needs=needs, time_budget=time_budget
    )
    selfhood = project_selfhood(history)
    held_values = developed_values(STARTING_VALUES, selfhood)
    possible_selves = [
        {
            "aspiration_id": item.aspiration_id,
            "kind": item.kind,
            "text": item.text,
            "value_id": item.value_id,
            "value_level": held_values.get(item.value_id, 0.7),
            "lived": item.lived,
            "strayed": item.strayed,
        }
        for item in selfhood.active_aspirations()
    ]
    choice_field = attended_impulses(
        history,
        decision_id=proposal_id,
        planning=planning,
        needs=needs,
        emotion=emotion,
        traits=traits,
        workspace=planning_workspace,
        opportunities=opportunities,
        preparation=preparation,
        time_budget=time_budget,
        current_location_id=current_location_id,
        possible_selves=possible_selves,
    )
    ongoing_activities = execution_context(history, planning, simulated_at)
    context: dict[str, object] = {
        "time": simulated_at.isoformat(),
        "available_opportunities": opportunities,
        "ongoing_activities": ongoing_activities,
        "household_tasks": [
            {"task": task, "pressure": "noticeable" if load < 0.5 else "piling up"}
            for task, load in project_household(history).loads.items()
            if load >= 0.25
        ]
        if current_location_id == "home"
        else [],
        "time_budget": time_budget,
        "preparation": preparation,
        "choice_field": choice_field,
        "current_location_id": current_location_id,
        "decision_cause": {"event_id": str(cause.event_id), "kind": cause.kind},
        "needs": dict(needs),
        "emotion": dict(emotion),
        "values": dict(values),
        "preferences": list(preferences),
        "traits": dict(traits),
        "recent_memories": list(memories[-8:]),
        "semantic_expectations": list(semantic_expectations[-8:]),
        "self_concepts": list(self_concepts[-4:]),
        "possible_selves": [
            {"kind": item["kind"], "text": item["text"], "value_id": item["value_id"]}
            for item in possible_selves
        ],
        "skills": list(skills[-12:]),
        "habits": list(habits[-6:]),
        "cognitive_workspace": list(planning_workspace[-12:]),
        "recent_activity_patterns": recent_activity_patterns,
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
            "Translate only chosen_impulse into a feasible proposed activity. The motivational choice "
            "has already happened; scheduling constraints must not replace it with an easier or more "
            'obvious alternative. Return {"no_change": true, "mode": "defer"} if that intention cannot '
            "be made concrete now. Wanting something is not permission to book it. Only output an "
            "activity when its start time and duration are deliberately specified. "
            "activity_type is a machine identifier of 3–40 lowercase letters, digits or underscores, such as letter_writing, never a phrase with spaces. priority is a fraction from 0 to 1, not a rank like 2 or 3. location_id is where the chosen activity will happen; travel there is handled separately, not disguised as learning at the place you are leaving. "
            "For an already-chosen dishwashing intention, use activity_type household_dishes, action work, and resource_id none. Household provisions are food, never dishwashing equipment. For an already-chosen food intention, use activity_type prepare_and_eat_meal and action work, at home or cafe. These identifiers are execution contracts, not suggestions for what to want. "
            "A work start or accepted appointment can be fixed without fixing the morning around it. "
            "Use time_budget after travel and current energy: a short window may suit a smaller "
            "version, skipping optional preparation, or leaving something unfinished. With spare "
            "time he may linger, do more, or simply rest; no daily preparation checklist is required. "
            "preparation describes optional scales and competing pulls, not instructions. A five-minute "
            "batch and a longer wash leave different amounts of mess. Choose scope and time together; "
            "you cannot compress the same result into any available gap. Leave room for uncertainty "
            "if that matters to him. "
            "Fractional hours allow ordinary short choices: 0.25 is fifteen minutes. "
            "estimate_confidence is his confidence in the duration estimate from 0 to 1. Use 1 only "
            "when duration is genuinely fixed; ordinary work is usually uncertain. The world, not the "
            "proposal, decides the actual effort required. "
            "Ongoing activities are evidence of effort, not proof the task succeeded. "
            "The activity "
            "type is open vocabulary. This is only a proposal: do not say it happened, spend money, "
            "create possessions, or guarantee another person's attendance. Use none when no object "
            "or companion is needed."
        ),
    }
    attended = impulse_attention_event(choice_field, proposal_id, cause, simulated_at)
    output = [attended]
    deliberation_context = {
        key: context[key]
        for key in (
            "time",
            "current_location_id",
            "choice_field",
            "current_attention",
            "emotion",
            "values",
            "preferences",
            "traits",
            "possible_selves",
        )
    }
    deliberation_context["permission"] = (
        "Choose only among attended impulses. Strength is felt pressure, not a score to maximize. "
        "Pursue exactly one, or continue, wait, defer, or do nothing. Do not plan timing, choose an "
        "action type, inspect feasibility, or recover an unattended alternative."
    )
    deliberation_request = ModelRequest(
        capability="pathos_deliberation",
        task_version="1",
        temperature=0.85,
        max_output_tokens=128,
        output_schema=_deliberation_schema(choice_field),
        messages=(ModelMessage("user", json.dumps(deliberation_context)),),
    )
    deliberation_requested = DomainEvent(
        "agency.deliberation_requested",
        "pathos",
        {
            "proposal_id": proposal_id,
            "source_event_id": str(cause.event_id),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=attended.event_id,
        correlation_id=proposal_id,
    )
    output.append(deliberation_requested)
    deliberation_trace_id = str(uuid4())
    deliberation_started = perf_counter()
    deliberation_response = None
    try:
        deliberation_response = await asyncio.wait_for(
            gateway.generate(deliberation_request), timeout=50
        )
        if deliberation_response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "Deliberation was incomplete")
        raw_deliberation = json.loads(deliberation_response.content)
        no_change_mode = _no_change_mode(raw_deliberation)
        if no_change_mode is not None:
            output.append(
                _trace(
                    "ok",
                    deliberation_trace_id,
                    simulated_at,
                    deliberation_started,
                    deliberation_response.resolved_model,
                    deliberation_response.backend,
                    None,
                    role="pathos_deliberation",
                )
            )
            choice = DomainEvent(
                "agency.choice_made",
                "pathos",
                {
                    "proposal_id": proposal_id,
                    "decision": no_change_mode,
                    "new_plan": False,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=attended.event_id,
                correlation_id=proposal_id,
            )
            output.extend(
                (
                    choice,
                    DomainEvent(
                        "agency.left_unplanned",
                        "pathos",
                        {
                            "proposal_id": proposal_id,
                            "decision": no_change_mode,
                            "simulated_at": simulated_at.isoformat(),
                        },
                        causation_id=choice.event_id,
                        correlation_id=proposal_id,
                    ),
                )
            )
            return output
        chosen_impulse_id, stated_intention = _parse_deliberation_choice(
            raw_deliberation, choice_field
        )
    except (KeyError, OSError, TimeoutError, TypeError, ValueError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "deliberation_failed"
        output.extend(
            (
                DomainEvent(
                    "role.failed",
                    "pathos",
                    {
                        "role": "pathos_deliberation",
                        "proposal_id": proposal_id,
                        "text": f"Private deliberation rejected: {error}",
                        "error_code": code,
                        "simulated_at": simulated_at.isoformat(),
                        "trace_id": deliberation_trace_id,
                    },
                    correlation_id=proposal_id,
                ),
                _trace(
                    "failed",
                    deliberation_trace_id,
                    simulated_at,
                    deliberation_started,
                    deliberation_response.resolved_model
                    if deliberation_response
                    else getattr(gateway, "model", "unknown"),
                    deliberation_response.backend if deliberation_response else "unknown",
                    code,
                    role="pathos_deliberation",
                ),
            )
        )
        return output
    chosen_impulse = next(
        item
        for item in _attended_impulse_items(choice_field)
        if item["impulse_id"] == chosen_impulse_id
    )
    output.append(
        _trace(
            "ok",
            deliberation_trace_id,
            simulated_at,
            deliberation_started,
            deliberation_response.resolved_model,
            deliberation_response.backend,
            None,
            role="pathos_deliberation",
        )
    )
    chosen = DomainEvent(
        "agency.impulse_chosen",
        "pathos",
        {
            "proposal_id": proposal_id,
            "impulse_id": chosen_impulse_id,
            "impulse_kind": chosen_impulse["kind"],
            "impulse_description": chosen_impulse["description"],
            "stated_intention": stated_intention,
            "simulated_at": simulated_at.isoformat(),
            "action_authority": False,
        },
        causation_id=attended.event_id,
        correlation_id=proposal_id,
    )
    output.append(chosen)
    context["chosen_impulse"] = {
        **chosen_impulse,
        "stated_intention": stated_intention,
        "meaning": "This is the chosen intention. Scheduling may implement or defer it, not replace it.",
    }
    chosen_source_context = next(
        (
            item
            for item in planning_workspace
            if item.get("source_event_id") == chosen_impulse.get("target_id")
        ),
        None,
    )
    if chosen_source_context is None and chosen_impulse.get("kind") == "aspiration":
        chosen_source_context = next(
            (
                {
                    "kind": "possible_self",
                    "aspiration_kind": item["kind"],
                    "text": item["text"],
                    "value_id": item["value_id"],
                    "epistemic_status": "possible_self",
                    "action_authority": False,
                }
                for item in possible_selves
                if item["aspiration_id"] == chosen_impulse.get("target_id")
            ),
            None,
        )
    if chosen_source_context is not None:
        context["chosen_source_context"] = chosen_source_context
    for motivational_key in (
        "choice_field",
        "available_opportunities",
        "household_tasks",
        "needs",
        "emotion",
        "values",
        "preferences",
        "traits",
        "recent_memories",
        "semantic_expectations",
        "self_concepts",
        "possible_selves",
        "skills",
        "habits",
        "recent_activity_patterns",
        "cognitive_workspace",
        "current_attention",
    ):
        context.pop(motivational_key, None)
    request = ModelRequest(
        capability="pathos_agency",
        task_version="11",
        temperature=0.9,
        max_output_tokens=320,
        output_schema=_agency_choice_schema(
            agency_output_schema(list(places), list(resources), list(people))
        ),
        messages=(ModelMessage("user", json.dumps(context)),),
    )
    requested = DomainEvent(
        "agency.generation_requested",
        "pathos",
        {
            "proposal_id": proposal_id,
            "source_event_id": str(cause.event_id),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=chosen.event_id,
        correlation_id=proposal_id,
    )
    output.append(requested)
    trace_id = str(uuid4())
    started = perf_counter()
    response = None
    try:
        response = await asyncio.wait_for(gateway.generate(request), timeout=50)
        if response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "Agency proposal was incomplete")
        raw_choice = json.loads(response.content)
        no_change_mode = _no_change_mode(raw_choice)
        if no_change_mode is not None:
            output.append(
                _trace(
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
                    "agency.choice_made",
                    "pathos",
                    {
                        "proposal_id": proposal_id,
                        "decision": no_change_mode,
                        "new_plan": False,
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=chosen.event_id,
                    correlation_id=proposal_id,
                )
            )
            output.append(
                DomainEvent(
                    "agency.left_unplanned",
                    "pathos",
                    {
                        "proposal_id": proposal_id,
                        "decision": no_change_mode,
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=output[-1].event_id,
                    correlation_id=proposal_id,
                )
            )
            return output
        candidate = parse_agency_candidate(
            response.content,
            completed_activity_titles=[
                str(item["title"])
                for item in ongoing_activities
                if item.get("outcome") == "completed"
            ],
        )
        _validate_choice_alignment(candidate.activity_type, chosen_impulse)
        if candidate.location_id != current_location_id:
            if current_location_id is None:
                if candidate.starts_in_hours == 0:
                    raise ProposalRejected(
                        "travel_required", "Starting now requires already being at the place"
                    )
            elif route_duration(
                current_location_id, candidate.location_id, catalog.route_minutes
            ) > timedelta(hours=candidate.starts_in_hours):
                raise ProposalRejected(
                    "travel_required", "The chosen start leaves too little time to get there"
                )
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
        recent_activity_signatures=[
            (
                str(item["activity_type"]),
                str(item["location_id"]),
                str(item["companion_id"]),
            )
            for item in recent_activity_patterns
        ],
    )
    output.extend(resolution.events)
    proposed = next(
        (event for event in resolution.events if event.kind == "agency.activity_proposed"), None
    )
    if proposed is not None:
        output.append(
            DomainEvent(
                "agency.choice_made",
                "pathos",
                {
                    "proposal_id": proposal_id,
                    "decision": "new_plan" if resolution.accepted else "attempt_rejected",
                    "new_plan": resolution.accepted,
                    "activity_type": candidate.activity_type,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=chosen.event_id,
                correlation_id=proposal_id,
            )
        )
    proposed_activity = next(
        (event for event in resolution.events if event.kind == "agency.activity_proposed"), None
    )
    if (
        resolution.accepted
        and proposed_activity is not None
        and proposed_activity.payload.get("activity_type") == "plan_reconsideration"
        and isinstance(planning_question, Mapping)
    ):
        schedule = next(
            (event for event in resolution.events if event.kind == "schedule.created"), None
        )
        source_id = planning_question.get("source_event_id")
        target_type = planning_question.get("target_type")
        target_id = planning_question.get("target_id")
        if schedule is not None and all(
            isinstance(value, str) and value.strip()
            for value in (source_id, target_type, target_id)
        ):
            output.append(
                DomainEvent(
                    "reflection.reconsideration_scheduled",
                    "pathos",
                    {
                        "source_reconsideration_event_id": source_id,
                        "activity_schedule_id": schedule.payload["schedule_id"],
                        "target_type": target_type,
                        "target_id": target_id,
                        "simulated_at": simulated_at.isoformat(),
                        "action_authority": False,
                    },
                    causation_id=schedule.event_id,
                    correlation_id=str(source_id),
                )
            )
    output.extend(
        dream_plan_link_events(history, planning_workspace, resolution.events, simulated_at)
    )
    return output


def _deliberation_schema(choice_field: Mapping[str, object]) -> dict[str, object]:
    impulse_ids = _pursuable_impulse_ids(choice_field)
    choices: list[dict[str, object]] = [
        {
            "type": "object",
            "properties": {"no_change": {"const": True}},
            "required": ["no_change"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {
                "no_change": {"const": True},
                "mode": {
                    "type": "string",
                    "enum": ["continue", "wait", "defer", "do_nothing"],
                },
            },
            "required": ["no_change", "mode"],
            "additionalProperties": False,
        },
    ]
    if impulse_ids:
        choices.insert(
            0,
            {
                "type": "object",
                "properties": {
                    "mode": {"const": "pursue"},
                    "chosen_impulse_id": {"type": "string", "enum": impulse_ids},
                    "intention": {"type": "string", "minLength": 4, "maxLength": 160},
                },
                "required": ["mode", "chosen_impulse_id", "intention"],
                "additionalProperties": False,
            },
        )
    return {"anyOf": choices}


def _parse_deliberation_choice(
    value: object, choice_field: Mapping[str, object]
) -> tuple[str, str]:
    if not isinstance(value, dict) or set(value) != {
        "mode",
        "chosen_impulse_id",
        "intention",
    }:
        raise ProposalRejected("invalid_deliberation", "Deliberation shape did not match")
    if value.get("mode") != "pursue":
        raise ProposalRejected("invalid_deliberation", "Unknown deliberation mode")
    impulse_id, intention = value.get("chosen_impulse_id"), value.get("intention")
    allowed = set(_pursuable_impulse_ids(choice_field))
    if not isinstance(impulse_id, str) or impulse_id not in allowed:
        raise ProposalRejected("unattended_choice", "The chosen impulse never reached attention")
    if not isinstance(intention, str) or not 4 <= len(intention.strip()) <= 160:
        raise ProposalRejected("invalid_intention", "The stated intention is not usable")
    return impulse_id, intention.strip()


def _pursuable_impulse_ids(choice_field: Mapping[str, object]) -> list[str]:
    """Return impulses that can become new work rather than a quiet-mode choice."""
    return [
        str(item["impulse_id"])
        for item in _attended_impulse_items(choice_field)
        if isinstance(item.get("impulse_id"), str)
        and item.get("kind") not in {"inaction", "continuation", "prospective"}
    ]


def _attended_impulse_items(choice_field: Mapping[str, object]) -> list[Mapping[str, object]]:
    attended = choice_field.get("attended_impulses", ())
    if not isinstance(attended, (list, tuple)):
        return []
    return [item for item in attended if isinstance(item, Mapping)]


def _validate_choice_alignment(activity_type: str, chosen_impulse: Mapping[str, object]) -> None:
    kind = chosen_impulse.get("kind")
    target_id = chosen_impulse.get("target_id")
    if kind == "domestic" and target_id == "dishes" and activity_type != "household_dishes":
        raise ProposalRejected("choice_drift", "The plan abandoned the chosen dish intention")
    if activity_type == "household_dishes" and not (kind == "domestic" and target_id == "dishes"):
        raise ProposalRejected("choice_drift", "Dishes were not the chosen intention")
    if kind == "need" and target_id == "hunger" and activity_type not in _MEAL_ACTIVITY_TYPES:
        raise ProposalRejected("choice_drift", "The plan abandoned the chosen need for food")
    if activity_type in _MEAL_ACTIVITY_TYPES and not (kind == "need" and target_id == "hunger"):
        raise ProposalRejected("choice_drift", "Food was not the chosen intention")
    if chosen_impulse.get("epistemic_status") == "planning_question" and (
        activity_type != "plan_reconsideration"
    ):
        raise ProposalRejected("choice_drift", "The plan abandoned the chosen question")
    if activity_type == "plan_reconsideration" and (
        chosen_impulse.get("epistemic_status") != "planning_question"
    ):
        raise ProposalRejected("choice_drift", "No reconsideration question was chosen")
    if kind in {"inaction", "continuation", "prospective"}:
        raise ProposalRejected(
            "choice_drift", "This impulse calls for continuing or waiting, not a substitute plan"
        )


def _agency_choice_schema(candidate: Mapping[str, object]) -> dict[str, object]:
    return {
        "anyOf": [
            candidate,
            {
                "type": "object",
                "properties": {"no_change": {"const": True}},
                "required": ["no_change"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "no_change": {"const": True},
                    "mode": {
                        "type": "string",
                        "enum": ["continue", "wait", "defer", "do_nothing"],
                    },
                },
                "required": ["no_change", "mode"],
                "additionalProperties": False,
            },
        ]
    }


def _no_change_mode(value: object) -> str | None:
    if value == {"no_change": True}:
        return "continue_or_wait"
    if (
        isinstance(value, dict)
        and value.get("no_change") is True
        and set(value) == {"no_change", "mode"}
        and value.get("mode") in {"continue", "wait", "defer", "do_nothing"}
    ):
        return str(value["mode"])
    return None


def _trace(
    status: str,
    trace_id: str,
    simulated_at: datetime,
    started: float,
    model: str,
    backend: str,
    error_code: str | None,
    *,
    role: str = "pathos_agency",
) -> DomainEvent:
    return DomainEvent(
        "role.completed",
        "pathos",
        {
            "role": role,
            "status": status,
            "model": model,
            "backend": backend,
            "latency_ms": max(0, round((perf_counter() - started) * 1000)),
            "error_code": error_code,
            "simulated_at": simulated_at.isoformat(),
            "trace_id": trace_id,
        },
    )


def _recent_activity_patterns(
    history: Sequence[DomainEvent], simulated_at: datetime
) -> list[dict[str, str]]:
    window_start = simulated_at - timedelta(days=21)
    patterns: list[dict[str, str]] = []
    for event in history:
        if event.kind != "agency.activity_realized" or event.aggregate_id != "pathos":
            continue
        value = event.payload.get("simulated_at")
        activity_type = event.payload.get("activity_type")
        location_id = event.payload.get("location_id")
        if not all(isinstance(item, str) for item in (value, activity_type, location_id)):
            continue
        at = datetime.fromisoformat(str(value))
        if at.utcoffset() is None or not window_start <= at <= simulated_at:
            continue
        companion = event.payload.get("companion_id")
        patterns.append(
            {
                "activity_type": str(activity_type),
                "location_id": str(location_id),
                "companion_id": companion if isinstance(companion, str) else "solo",
                "realized_at": at.isoformat(),
            }
        )
    return patterns[-10:]
