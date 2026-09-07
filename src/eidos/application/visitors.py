"""Replay-stable visitor plans and interruptions sourced from connection goals."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import AbstractSet, Mapping, Sequence

from eidos.application.interruption_recovery import recover_user_scene
from eidos.domain.events import DomainEvent
from eidos.domain.relationships import Relationship
from eidos.domain.scenes import (
    SceneInterruptProposal,
    project_scenes,
    resolve_scene_interruption,
)


def visitor_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    *,
    actor_locations: Mapping[str, str],
    pathos_awake: bool,
    pathos_energy: float,
    social_openness: float,
    relationships: Mapping[str, Relationship],
    known_person_ids: AbstractSet[str] | None = None,
) -> list[DomainEvent]:
    """Advance one visit lifecycle, or reserve one eligible connection goal."""
    completed = _complete_admitted_visit(
        history, simulated_at, actual_revision, actor_locations, pathos_energy
    )
    if completed:
        return completed
    due = _resolve_due_plan(
        history,
        simulated_at,
        actual_revision,
        actor_locations,
        pathos_awake,
        pathos_energy,
        social_openness,
        relationships,
    )
    if due:
        return due
    handled_goal_ids = {
        str(event.payload["source_goal_id"])
        for event in history
        if event.kind in {"visitor.planned", "phone.call_received"}
        and isinstance(event.payload.get("source_goal_id"), str)
    }
    goal = next(
        (
            event
            for event in history
            if event.kind == "npc.goal_formed"
            and event.payload.get("motivation_need") == "connection"
            and (known_person_ids is None or event.payload.get("actor_id") in known_person_ids)
            and str(event.payload.get("goal_id")) not in handled_goal_ids
        ),
        None,
    )
    if goal is None:
        return []
    goal_id = str(goal.payload["goal_id"])
    visitor_id = str(goal.payload["actor_id"])
    visit_id = f"{visitor_id}-connection-visit-{goal_id}"
    if _sample(visit_id) >= 0.35:
        return []
    arrives_at = (simulated_at + timedelta(days=1)).replace(
        hour=18, minute=0, second=0, microsecond=0
    )
    return [
        DomainEvent(
            "visitor.planned",
            "pathos",
            {
                "visit_id": visit_id,
                "visitor_id": visitor_id,
                "source_goal_id": goal_id,
                "purpose": str(goal.payload["title"]),
                "arrives_at": arrives_at.isoformat(),
                "location_id": "home",
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=goal.event_id,
            correlation_id=visit_id,
        )
    ]


def visitor_locations(history: Sequence[DomainEvent]) -> Mapping[str, str]:
    """Return admitted visitors whose departure is not yet in history."""
    departed = {
        str(event.payload["visit_id"]) for event in history if event.kind == "visitor.departed"
    }
    return {
        str(event.payload["visitor_id"]): str(event.payload["location_id"])
        for event in history
        if event.kind == "visitor.admitted" and str(event.payload["visit_id"]) not in departed
    }


def _resolve_due_plan(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    actor_locations: Mapping[str, str],
    pathos_awake: bool,
    pathos_energy: float,
    social_openness: float,
    relationships: Mapping[str, Relationship],
) -> list[DomainEvent]:
    resolved = {
        str(event.payload["visit_id"])
        for event in history
        if event.kind in {"visitor.arrived", "visitor.missed"}
    }
    planned = next(
        (
            event
            for event in history
            if event.kind == "visitor.planned"
            and str(event.payload["visit_id"]) not in resolved
            and datetime.fromisoformat(str(event.payload["arrives_at"])) <= simulated_at
        ),
        None,
    )
    if planned is None:
        return []
    visit_id = str(planned.payload["visit_id"])
    visitor_id = str(planned.payload["visitor_id"])
    if not pathos_awake or actor_locations.get("pathos") != "home":
        return [
            DomainEvent(
                "visitor.missed",
                "pathos",
                {
                    "visit_id": visit_id,
                    "visitor_id": visitor_id,
                    "reason": "Pathos was asleep or away when the visitor arrived.",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=planned.event_id,
                correlation_id=visit_id,
            )
        ]
    arrived = DomainEvent(
        "visitor.arrived",
        "pathos",
        {
            "visit_id": visit_id,
            "visitor_id": visitor_id,
            "location_id": "home",
            "text": f"{visitor_id.replace('-', ' ').title()} came to the door.",
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=planned.event_id,
        correlation_id=visit_id,
    )
    relationship = relationships.get(visitor_id, Relationship(visitor_id))
    threshold = max(
        0.05,
        min(
            0.95,
            0.3
            + 0.25 * social_openness
            + 0.2 * pathos_energy
            + 0.12 * relationship.familiarity
            + 0.08 * relationship.trust
            - 0.18 * relationship.tension,
        ),
    )
    if _sample(f"admit-{visit_id}") >= threshold:
        return [
            arrived,
            DomainEvent(
                "visitor.deferred",
                "pathos",
                {
                    "visit_id": visit_id,
                    "visitor_id": visitor_id,
                    "reason": "Pathos did not have enough room for an unplanned conversation.",
                    "decision_energy": pathos_energy,
                    "decision_social_openness": social_openness,
                    "decision_familiarity": relationship.familiarity,
                    "decision_tension": relationship.tension,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=arrived.event_id,
                correlation_id=visit_id,
            ),
        ]
    user_scene = next(
        (
            scene
            for scene in project_scenes(history).scenes.values()
            if scene.status == "active"
            and {scene.initiator_id, scene.partner_id} == {"pathos", "user"}
        ),
        None,
    )
    admitted = DomainEvent(
        "visitor.admitted",
        "pathos",
        {
            "visit_id": visit_id,
            "visitor_id": visitor_id,
            "location_id": "home",
            "scene_id": user_scene.scene_id if user_scene else None,
            "text": f"Pathos invited {visitor_id.replace('-', ' ').title()} inside.",
            "decision_energy": pathos_energy,
            "decision_social_openness": social_openness,
            "decision_familiarity": relationship.familiarity,
            "decision_tension": relationship.tension,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=arrived.event_id,
        correlation_id=visit_id,
    )
    output = [arrived, admitted, _visit_memory(admitted, simulated_at)]
    if user_scene is None:
        output.append(_relationship_effect(admitted, simulated_at))
        return output
    interrupted = resolve_scene_interruption(
        SceneInterruptProposal(
            f"visitor-interrupt-{visit_id}",
            user_scene.scene_id,
            "pathos",
            arrived.event_id,
            actual_revision + len(output),
        ),
        state=project_scenes([*history, *output]),
        history=[*history, *output],
        actual_revision=actual_revision + len(output),
        simulated_at=simulated_at.isoformat(),
    )
    output.extend(interrupted.events)
    output.append(
        DomainEvent(
            "conversation.message",
            "pathos",
            {
                "speaker": "system",
                "text": f"{visitor_id.replace('-', ' ').title()} arrived; Pathos stepped away to answer the door.",
                "channel": "live_visit",
                "scene_id": user_scene.scene_id,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=admitted.event_id,
            correlation_id=user_scene.scene_id,
        )
    )
    return output


def _complete_admitted_visit(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    actor_locations: Mapping[str, str],
    pathos_energy: float,
) -> list[DomainEvent]:
    departed = {
        str(event.payload["visit_id"]) for event in history if event.kind == "visitor.departed"
    }
    admitted = next(
        (
            event
            for event in history
            if event.kind == "visitor.admitted"
            and str(event.payload["visit_id"]) not in departed
            and datetime.fromisoformat(str(event.payload["simulated_at"])) < simulated_at
        ),
        None,
    )
    if admitted is None:
        return []
    departed_event = DomainEvent(
        "visitor.departed",
        "pathos",
        {
            "visit_id": str(admitted.payload["visit_id"]),
            "visitor_id": str(admitted.payload["visitor_id"]),
            "text": (
                f"{str(admitted.payload['visitor_id']).replace('-', ' ').title()} "
                "said goodbye and left."
            ),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=admitted.event_id,
        correlation_id=admitted.correlation_id,
    )
    output = [departed_event, _relationship_effect(admitted, simulated_at)]
    scene_id = admitted.payload.get("scene_id")
    scene = project_scenes(history).scenes.get(str(scene_id)) if scene_id else None
    if scene is not None and scene.status == "paused":
        output.extend(
            recover_user_scene(
                [*history, *output],
                scene.scene_id,
                simulated_at,
                actual_revision + len(output),
                actor_locations=actor_locations,
                pathos_energy=pathos_energy,
                source_event=departed_event,
                decision_key=f"visitor-{admitted.payload['visit_id']}",
            )
        )
    return output


def _visit_memory(admitted: DomainEvent, simulated_at: datetime) -> DomainEvent:
    visitor_id = str(admitted.payload["visitor_id"])
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": f"{visitor_id.replace('-', ' ').title()} stopped by for an ordinary visit.",
            "owner": "pathos",
            "category": "encounter",
            "source": "visitor-lifecycle",
            "source_event_id": str(admitted.event_id),
            "person_id": visitor_id,
            "location_id": "home",
            "importance": 0.55,
            "confidence": 1.0,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=admitted.event_id,
        correlation_id=admitted.correlation_id,
    )


def _relationship_effect(admitted: DomainEvent, simulated_at: datetime) -> DomainEvent:
    return DomainEvent(
        "relationship.changed",
        "pathos",
        {
            "person_id": str(admitted.payload["visitor_id"]),
            "evidence_actor_id": "pathos",
            "familiarity_delta": 0.03,
            "trust_delta": 0.0,
            "reason": "They made time for an ordinary visit.",
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=admitted.event_id,
        correlation_id=admitted.correlation_id,
    )


def _sample(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
