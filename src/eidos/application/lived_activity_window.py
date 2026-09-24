"""Order arrival, elapsed work, completion, then departure at shared boundaries."""

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Sequence

from eidos.application.activity_execution import (
    _timeline_events,
    _timeline_since,
    execution_events,
)
from eidos.application.dream_planning import dream_plan_outcome_events, dream_project_outcome_events
from eidos.application.personal_journeys import journey_window_events
from eidos.application.phone_calls import complete_answered_call
from eidos.application.reconsideration_decisions import reconsideration_decision_events
from eidos.application.scheduled_activity import scheduled_activity_events
from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, events_of
from eidos.domain.npcs import project_npcs
from eidos.domain.planning import PlanningState, project_planning
from eidos.domain.scenes import project_scenes
from eidos.domain.state import PathosState
from eidos.domain.world_catalog import WorldCatalog


def _visible_state_step(state: PathosState, event: DomainEvent) -> PathosState:
    # Time-ordered windows can place a meal before the clock event that preceded it in
    # history; align the clock so the meal validates against its own moment.
    if event.kind == "meal.eaten" and isinstance(event.payload.get("simulated_at"), str):
        state = replace(
            state, simulated_at=datetime.fromisoformat(str(event.payload["simulated_at"]))
        )
    return state.apply(event)


_VISIBLE_STATE: IncrementalFold[PathosState] = IncrementalFold(
    PathosState, _visible_state_step, capacity=8
)


def lived_activity_window(
    history: Sequence[DomainEvent],
    planning: PlanningState,
    catalog: WorldCatalog,
    since: datetime,
    now: datetime,
    *,
    repair_mastery: float,
    available_pence: int = 0,
) -> list[DomainEvent]:
    journeys = journey_window_events(history, planning, catalog, since, now)
    closed_calls = {e.payload.get("call_id") for e in events_of(history, "phone.call_completed")}
    calls = [
        e
        for e in events_of(history, "phone.call_answered")
        if e.payload.get("call_id") not in closed_calls
    ]
    if (
        not calls
        and not journeys
        and not any(
            e.status == "scheduled"
            and e.action in {"work", "learn", "attend", "repair"}
            and datetime.fromisoformat(e.starts_at) <= now
            for e in planning.calendar.values()
        )
    ):
        return []
    points = {since, now}
    for call in calls:
        if call.payload.get("ends_at"):
            end = datetime.fromisoformat(str(call.payload["ends_at"]))
            if since <= end <= now:
                points.add(end)
    relevant = {
        "sleep.ended",
        "sleep.started",
        "scene.started",
        "scene.ended",
        "scene.interrupted",
        "scene.resumed",
        "incident.response_started",
        "incident.response_completed",
        "incident.response_abandoned",
        "pathos.moved",
        "pathos.travel_started",
        "pathos.travel_arrived",
        "object.custody_changed",
        "phone.call_answered",
        "phone.call_completed",
        "object.condition_changed",
    }
    for at, _, event in _timeline_since([*history, *journeys], since, now):
        if event.kind in relevant:
            points.add(at)
    for entry in planning.calendar.values():
        if entry.status != "scheduled":
            continue
        for raw in (entry.starts_at, entry.ends_at):
            if raw and since <= datetime.fromisoformat(raw) <= now:
                points.add(datetime.fromisoformat(raw))
    output: list[DomainEvent] = []
    ordered = sorted(points)
    processed: set[datetime] = set()
    while ordered:
        at = ordered.pop(0)
        if at in processed:
            continue
        processed.add(at)
        crossing = [e for e in journeys if e.payload["simulated_at"] == at.isoformat()]
        output.extend(e for e in crossing if e.kind != "pathos.travel_started")
        visible = _timeline_events([*history, *output] if output else history, at)
        projected = project_planning(visible)
        state = _VISIBLE_STATE(visible)
        visitor_scene = next(
            (
                s
                for s in project_scenes(visible).scenes.values()
                if s.status == "paused" and {s.initiator_id, s.partner_id} == {"pathos", "user"}
            ),
            None,
        )
        ended_calls = complete_answered_call(
            visible,
            at,
            len(history) + len(output),
            actor_locations={
                "pathos": state.location_id,
                "user": visitor_scene.location_id if visitor_scene else "absent",
            },
            pathos_energy=state.energy,
        )
        output.extend(ended_calls)
        visible.extend(ended_calls)
        execution = execution_events(visible, projected, at)
        output.extend(execution)
        visible.extend(execution)
        for event in execution:
            if event.kind not in {"activity.execution_started", "activity.execution_resumed"}:
                continue
            work_begins = (
                datetime.fromisoformat(str(event.payload["resume_after"]))
                if event.payload.get("resume_after")
                else at
            )
            completion_at = work_begins + timedelta(
                seconds=float(str(event.payload["remaining_seconds"]))
            )
            window_end = datetime.fromisoformat(str(event.payload["window_ends_at"]))
            if at < completion_at <= min(now, window_end) and completion_at not in processed:
                ordered.append(completion_at)
                ordered.sort()
        completed = scheduled_activity_events(
            projected,
            actor_location_id=state.location_id,
            simulated_at=at,
            actual_revision=len(history) + len(output),
            repair_mastery=repair_mastery,
            actor_locations={p: n.location_id for p, n in project_npcs(visible, at).people.items()}
            if any(e.status == "scheduled" and e.companion_id for e in projected.calendar.values())
            else {},
            cognitive_history=visible,
            cognitive_capacity=min(state.energy, state.rest),
            require_execution_evidence=True,
            actor_state=replace(state, simulated_at=at),
            available_pence=available_pence,
        )
        output.extend(completed)
        if completed:
            combined = [*history, *output]
            output.extend(dream_plan_outcome_events(combined, at))
            output.extend(dream_project_outcome_events([*history, *output], at))
            for realized in (e for e in completed if e.kind == "agency.activity_realized"):
                output.extend(
                    reconsideration_decision_events(
                        [*history, *output],
                        realized,
                        project_planning([*history, *output]),
                        len(history) + len(output),
                        at,
                    )
                )
        # At 10:40 a task can finish at home and then the next journey can begin.
        # Reversing this order loses legitimate completion because he is in transit.
        output.extend(e for e in crossing if e.kind == "pathos.travel_started")
    return output
