"""Bounded NPC belief formation from each actor's own accepted perceptions."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.beliefs import BeliefProposal, BeliefState, project_beliefs, resolve_belief
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import project_npcs
from eidos.domain.world import npc_plan_profile


def npc_belief_events(
    history: Sequence[DomainEvent],
    simulated_at: str,
    belief_state: BeliefState | None = None,
) -> list[DomainEvent]:
    """Turn unprocessed public-event perceptions into private, owned beliefs."""
    now = datetime.fromisoformat(simulated_at)
    if now.utcoffset() is None:
        raise ValueError("NPC cognition time must be timezone-aware")
    output: list[DomainEvent] = []
    state = belief_state if belief_state is not None else project_beliefs(history)
    npc_state = project_npcs(history, now)
    used_evidence = {
        str(event.payload["evidence_event_id"])
        for event in history
        if event.kind
        in {
            "belief.proposed",
            "belief.formed",
            "belief.revised",
            "belief.corrected",
            "belief.contested",
        }
        and isinstance(event.payload.get("evidence_event_id"), str)
    }
    latest_plan_at = _latest_plan_times(history)
    for perception in history:
        owner = perception.payload.get("owner")
        location_id = perception.payload.get("location_id")
        if (
            perception.kind != "perception.recorded"
            or perception.payload.get("source_kind") != "world_event"
            or not isinstance(owner, str)
            or owner == "pathos"
            or owner not in npc_state.people
            or not isinstance(location_id, str)
            or str(perception.event_id) in used_evidence
        ):
            continue
        belief_id = f"{owner}-{location_id}-community-activity"
        resolution = resolve_belief(
            BeliefProposal(
                proposal_id=f"interpret-{perception.event_id}",
                belief_id=belief_id,
                owner_id=owner,
                subject_id=location_id,
                predicate="community_activity",
                object_value="neighbors gather here",
                confidence=0.85,
                evidence_event_id=perception.event_id,
                expected_revision=len(history) + len(output),
            ),
            state=state,
            history=[*history, *output],
            actual_revision=len(history) + len(output),
            simulated_at=simulated_at,
        )
        output.extend(resolution.events)
        for event in resolution.events:
            state = state.apply(event)
        if resolution.accepted:
            used_evidence.add(str(perception.event_id))
            formed = next(
                (event for event in resolution.events if event.kind == "belief.formed"), None
            )
            if formed is None:
                continue
            if npc_state.people[owner].plan_status == "active" or _in_plan_cooldown(
                latest_plan_at.get(owner), now
            ):
                continue
            profile = npc_plan_profile(owner, location_id)
            scheduled_for = _next_noon(now)
            plan = DomainEvent(
                "npc.plan_created",
                "pathos",
                {
                    "actor_id": owner,
                    "plan_id": f"{owner}-community-response-{perception.event_id}",
                    "title": str(profile["title"]),
                    "action": str(profile["action"]),
                    "location_id": str(profile["location_id"]),
                    "scheduled_for": scheduled_for.isoformat(),
                    "due_at": (scheduled_for + timedelta(days=1)).isoformat(),
                    "belief_id": formed.payload["belief_id"],
                    "evidence_perception_id": str(perception.event_id),
                    "owner": owner,
                    "visibility": "private",
                    "simulated_at": simulated_at,
                },
                causation_id=formed.event_id,
                correlation_id=formed.correlation_id,
            )
            output.append(plan)
            npc_state = npc_state.apply(plan)
            latest_plan_at[owner] = now
    return output


def npc_need_plan_events(history: Sequence[DomainEvent], simulated_at: str) -> list[DomainEvent]:
    """Let private needs form bounded goals without leaking them into Pathos's context."""
    now = datetime.fromisoformat(simulated_at)
    if now.utcoffset() is None:
        raise ValueError("NPC cognition time must be timezone-aware")
    if now.hour != 19:
        return []
    state = project_npcs(history, now)
    used_evidence = {
        str(event.payload["evidence_need_event_id"])
        for event in history
        if event.kind == "npc.plan_created"
        and isinstance(event.payload.get("evidence_need_event_id"), str)
    }
    latest_plan_at = _latest_plan_times(history)
    output: list[DomainEvent] = []
    for actor_id, person in state.people.items():
        if person.plan_status == "active" or _in_plan_cooldown(latest_plan_at.get(actor_id), now):
            continue
        evidence = next(
            (
                event
                for event in reversed(history)
                if event.kind == "npc.needs_changed"
                and event.payload.get("actor_id") == actor_id
                and event.payload.get("owner") == actor_id
                and str(event.event_id) not in used_evidence
            ),
            None,
        )
        if evidence is None:
            continue
        needs = {
            "energy": person.energy,
            "connection": person.connection,
            "purpose": person.purpose,
        }
        need, level = min(needs.items(), key=lambda item: (item[1], item[0]))
        if level >= 0.58:
            continue
        action, location_id, title, scheduled_for = _need_plan(
            actor_id, need, now, person.usual_location_id
        )
        goal_id = f"{actor_id}-{need}-goal-{evidence.event_id}"
        motivation = f"restore {need} from {level:.2f}"
        goal = DomainEvent(
            "npc.goal_formed",
            "pathos",
            {
                "actor_id": actor_id,
                "goal_id": goal_id,
                "title": title,
                "motivation": motivation,
                "motivation_need": need,
                "evidence_need_event_id": str(evidence.event_id),
                "owner": actor_id,
                "visibility": "private",
                "simulated_at": simulated_at,
            },
            causation_id=evidence.event_id,
            correlation_id=f"npc-need-{actor_id}-{evidence.event_id}",
        )
        plan = DomainEvent(
            "npc.plan_created",
            "pathos",
            {
                "actor_id": actor_id,
                "plan_id": f"{actor_id}-{need}-{evidence.event_id}",
                "title": title,
                "action": action,
                "location_id": location_id,
                "scheduled_for": scheduled_for.isoformat(),
                "due_at": (scheduled_for + timedelta(hours=6)).isoformat(),
                "motivation": motivation,
                "motivation_need": need,
                "goal_id": goal_id,
                "evidence_need_event_id": str(evidence.event_id),
                "owner": actor_id,
                "visibility": "private",
                "simulated_at": simulated_at,
            },
            causation_id=goal.event_id,
            correlation_id=f"npc-need-{actor_id}-{evidence.event_id}",
        )
        output.extend((goal, plan))
        state = state.apply(goal).apply(plan)
        latest_plan_at[actor_id] = now
        used_evidence.add(str(evidence.event_id))
    return output


def _latest_plan_times(history: Sequence[DomainEvent]) -> dict[str, datetime]:
    latest: dict[str, datetime] = {}
    for event in history:
        if event.kind != "npc.plan_created":
            continue
        actor_id = event.payload.get("actor_id")
        value = event.payload.get("simulated_at")
        if not isinstance(actor_id, str) or not isinstance(value, str):
            continue
        try:
            at = datetime.fromisoformat(value)
        except ValueError:
            continue
        if at.utcoffset() is not None and (actor_id not in latest or latest[actor_id] < at):
            latest[actor_id] = at
    return latest


def _in_plan_cooldown(previous: datetime | None, now: datetime) -> bool:
    return previous is not None and now - previous < timedelta(days=7)


def _next_noon(now: datetime) -> datetime:
    candidate = now.replace(hour=12, minute=0, second=0, microsecond=0)
    return candidate if candidate > now else candidate + timedelta(days=1)


def _need_plan(
    actor_id: str, need: str, now: datetime, usual_location_id: str = "park"
) -> tuple[str, str, str, datetime]:
    if need == "energy":
        midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return "rest", "home", "Protect an unhurried stretch of rest", midnight
    if need == "connection" and actor_id == "ellis":
        evening = (now + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
        return "walk", "park", "Take an evening walk where neighbors may be around", evening
    profile = npc_plan_profile(actor_id, usual_location_id)
    title = (
        "Make room for people at the café"
        if actor_id == "mara" and need == "connection"
        else "Sketch among familiar people in the square"
        if actor_id == "rowan" and need == "connection"
        else str(profile["title"])
    )
    return (
        str(profile["action"]),
        str(profile["location_id"]),
        title,
        _next_noon(now),
    )
