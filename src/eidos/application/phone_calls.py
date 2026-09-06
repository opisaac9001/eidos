"""Causal phone interruptions arising from NPC connection goals."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.scenes import (
    SceneInterruptProposal,
    SceneResumeProposal,
    project_scenes,
    resolve_scene_interruption,
    resolve_scene_resume,
)


def phone_call_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    *,
    actor_locations: Mapping[str, str],
    pathos_awake: bool,
    pathos_energy: float = 0.5,
    social_openness: float = 0.5,
) -> list[DomainEvent]:
    """Advance existing calls, then allow one unmet connection goal to cause a call."""
    output = _complete_answered_call(
        history, simulated_at, actual_revision, actor_locations=actor_locations
    )
    if output:
        return output
    output = _complete_due_callback(history, simulated_at, pathos_awake=pathos_awake)
    if output:
        return output
    called_goal_ids = {
        str(event.payload["source_goal_id"])
        for event in history
        if event.kind == "phone.call_received" and "source_goal_id" in event.payload
    }
    goal = next(
        (
            event
            for event in history
            if event.kind == "npc.goal_formed"
            and event.payload.get("motivation_need") == "connection"
            and str(event.payload.get("goal_id")) not in called_goal_ids
        ),
        None,
    )
    if goal is None or not pathos_awake:
        return []
    caller_id = str(goal.payload["actor_id"])
    call_id = f"{caller_id}-connection-call-{goal.payload['goal_id']}"
    received = DomainEvent(
        "phone.call_received",
        "pathos",
        {
            "call_id": call_id,
            "caller_id": caller_id,
            "callee_id": "pathos",
            "purpose": str(goal.payload["title"]),
            "urgency": 0.35,
            "source_goal_id": str(goal.payload["goal_id"]),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=goal.event_id,
        correlation_id=call_id,
    )
    output = [received]
    scene = next(
        (
            item
            for item in project_scenes(history).scenes.values()
            if item.status == "active"
            and {item.initiator_id, item.partner_id} == {"pathos", "user"}
        ),
        None,
    )
    sample = int(sha256(call_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    answer_threshold = 0.25 + 0.35 * social_openness + 0.2 * pathos_energy
    answer = sample < answer_threshold
    if scene is not None and not answer:
        output.extend(
            (
                DomainEvent(
                    "phone.call_declined",
                    "pathos",
                    {
                        "call_id": call_id,
                        "reason": "Pathos chose not to leave the current conversation.",
                        "decision_energy": pathos_energy,
                        "decision_social_openness": social_openness,
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=received.event_id,
                    correlation_id=call_id,
                ),
                DomainEvent(
                    "phone.callback_scheduled",
                    "pathos",
                    {
                        "call_id": call_id,
                        "caller_id": caller_id,
                        "due_at": (simulated_at + timedelta(hours=2)).isoformat(),
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=received.event_id,
                    correlation_id=call_id,
                ),
            )
        )
        return output
    answered = DomainEvent(
        "phone.call_answered",
        "pathos",
        {
            "call_id": call_id,
            "caller_id": caller_id,
            "scene_id": scene.scene_id if scene else None,
            "decision_energy": pathos_energy,
            "decision_social_openness": social_openness,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=received.event_id,
        correlation_id=call_id,
    )
    output.append(answered)
    if scene is None:
        output.append(_call_completed(answered, simulated_at))
        return output
    interrupted = resolve_scene_interruption(
        SceneInterruptProposal(
            f"phone-interrupt-{call_id}",
            scene.scene_id,
            "pathos",
            received.event_id,
            actual_revision + len(output),
        ),
        state=project_scenes([*history, *output]),
        history=[*history, *output],
        actual_revision=actual_revision + len(output),
        simulated_at=simulated_at.isoformat(),
    )
    output.extend(interrupted.events)
    return output


def _complete_answered_call(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    *,
    actor_locations: Mapping[str, str],
) -> list[DomainEvent]:
    completed = {
        str(event.payload["call_id"])
        for event in history
        if event.kind in {"phone.call_completed", "phone.callback_completed"}
    }
    answered = next(
        (
            event
            for event in history
            if event.kind == "phone.call_answered"
            and str(event.payload["call_id"]) not in completed
            and datetime.fromisoformat(str(event.payload["simulated_at"])) < simulated_at
        ),
        None,
    )
    if answered is None:
        return []
    output = [_call_completed(answered, simulated_at)]
    scene_id = answered.payload.get("scene_id")
    scene = project_scenes(history).scenes.get(str(scene_id)) if scene_id else None
    if scene is not None and scene.status == "paused":
        resumed = resolve_scene_resume(
            SceneResumeProposal(
                f"phone-resume-{answered.payload['call_id']}",
                scene.scene_id,
                "pathos",
                actual_revision + len(output),
            ),
            state=project_scenes([*history, *output]),
            actor_locations=actor_locations,
            actual_revision=actual_revision + len(output),
            simulated_at=simulated_at.isoformat(),
        )
        output.extend(resumed.events)
    return output


def _complete_due_callback(
    history: Sequence[DomainEvent], simulated_at: datetime, *, pathos_awake: bool
) -> list[DomainEvent]:
    if not pathos_awake or any(
        scene.status == "active" and "pathos" in {scene.initiator_id, scene.partner_id}
        for scene in project_scenes(history).scenes.values()
    ):
        return []
    completed = {
        str(event.payload["call_id"])
        for event in history
        if event.kind == "phone.callback_completed"
    }
    due = next(
        (
            event
            for event in history
            if event.kind == "phone.callback_scheduled"
            and str(event.payload["call_id"]) not in completed
            and datetime.fromisoformat(str(event.payload["due_at"])) <= simulated_at
        ),
        None,
    )
    if due is None:
        return []
    return [
        DomainEvent(
            "phone.callback_completed",
            "pathos",
            {
                "call_id": str(due.payload["call_id"]),
                "caller_id": str(due.payload["caller_id"]),
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=due.event_id,
            correlation_id=due.correlation_id,
        )
    ]


def _call_completed(answered: DomainEvent, simulated_at: datetime) -> DomainEvent:
    return DomainEvent(
        "phone.call_completed",
        "pathos",
        {
            "call_id": str(answered.payload["call_id"]),
            "caller_id": str(answered.payload["caller_id"]),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=answered.event_id,
        correlation_id=answered.correlation_id,
    )
