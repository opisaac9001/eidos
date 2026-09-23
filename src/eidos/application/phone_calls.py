"""Causal phone interruptions arising from NPC connection goals."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import AbstractSet, Mapping, Sequence

from eidos.application.contact_pacing import contact_allowed
from eidos.application.interruption_recovery import recover_user_scene
from eidos.domain.events import DomainEvent
from eidos.domain.relationships import Relationship
from eidos.domain.scenes import (
    SceneInterruptProposal,
    project_scenes,
    resolve_scene_interruption,
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
    relationships: Mapping[str, Relationship] | None = None,
    known_person_ids: AbstractSet[str] | None = None,
    instant_calls: bool = True,
    attention_absorption: float = 0.0,
    paced: bool = False,
) -> list[DomainEvent]:
    """Advance existing calls, then allow one unmet connection goal to cause a call."""
    output = complete_answered_call(
        history,
        simulated_at,
        actual_revision,
        actor_locations=actor_locations,
        pathos_energy=pathos_energy,
    )
    if output:
        return output
    output = _notice_due_notification(history, simulated_at, pathos_awake=pathos_awake)
    if output:
        return output
    closed = {e.payload.get("call_id") for e in history if e.kind == "phone.call_completed"}
    if any(
        e.kind == "phone.call_answered" and e.payload.get("call_id") not in closed for e in history
    ):
        return []
    output = _complete_due_callback(history, simulated_at, pathos_awake=pathos_awake)
    if output:
        return output
    called_goal_ids = {
        str(event.payload["source_goal_id"])
        for event in history
        if event.kind in {"phone.call_received", "visitor.planned"}
        and "source_goal_id" in event.payload
    }
    goal = next(
        (
            event
            for event in history
            if event.kind == "npc.goal_formed"
            and event.payload.get("motivation_need") == "connection"
            and (known_person_ids is None or event.payload.get("actor_id") in known_person_ids)
            and str(event.payload.get("goal_id")) not in called_goal_ids
            and (
                not paced
                or contact_allowed(history, str(event.payload.get("actor_id")), event, simulated_at)
            )
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
    notice_sample = int(sha256(f"notice:{call_id}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    # Deep focus makes a buzzing phone easy to miss, but most calls still get noticed:
    # people glance at their phones even mid-task.
    notice_probability = max(0.08, min(0.98, 0.94 - 0.45 * attention_absorption))
    if not instant_calls and notice_sample >= notice_probability:
        notice_after = simulated_at + timedelta(minutes=5 + round(notice_sample * 35))
        output.append(
            DomainEvent(
                "phone.call_missed",
                "pathos",
                {
                    "call_id": call_id,
                    "caller_id": caller_id,
                    "reason": "The call did not break through his current focus in time.",
                    "attention_absorption": attention_absorption,
                    "notice_probability": notice_probability,
                    "notice_after": notice_after.isoformat(),
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=received.event_id,
                correlation_id=call_id,
            )
        )
        return output
    relationship = (
        relationships.get(caller_id, Relationship(caller_id))
        if relationships is not None
        else Relationship(caller_id)
    )
    relationship_pull = (
        0.12 * (relationship.trust - 0.3)
        + 0.08 * (relationship.familiarity - 0.2)
        - 0.15 * relationship.tension
    )
    answer_threshold = max(
        0.05,
        min(
            0.95,
            0.25 + 0.35 * social_openness + 0.2 * pathos_energy + relationship_pull,
        ),
    )
    answer = sample < answer_threshold
    if not answer and (scene is not None or not instant_calls):
        output.extend(
            (
                DomainEvent(
                    "phone.call_declined",
                    "pathos",
                    {
                        "call_id": call_id,
                        "reason": (
                            "Pathos chose not to leave the current conversation."
                            if scene is not None
                            else "Pathos chose not to interrupt what he was doing."
                        ),
                        "decision_energy": pathos_energy,
                        "decision_social_openness": social_openness,
                        "decision_trust": relationship.trust,
                        "decision_familiarity": relationship.familiarity,
                        "decision_tension": relationship.tension,
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
            **(
                {"ends_at": (simulated_at + timedelta(minutes=3 + round(sample * 9))).isoformat()}
                if not instant_calls
                else {}
            ),
            "decision_energy": pathos_energy,
            "decision_social_openness": social_openness,
            "decision_trust": relationship.trust,
            "decision_familiarity": relationship.familiarity,
            "decision_tension": relationship.tension,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=received.event_id,
        correlation_id=call_id,
    )
    output.append(answered)
    if scene is None:
        if instant_calls:
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


def _notice_due_notification(
    history: Sequence[DomainEvent], simulated_at: datetime, *, pathos_awake: bool
) -> list[DomainEvent]:
    if not pathos_awake:
        return []
    noticed = {
        str(event.payload["call_id"])
        for event in history
        if event.kind == "phone.notification_noticed"
    }
    missed = next(
        (
            event
            for event in history
            if event.kind == "phone.call_missed"
            and str(event.payload["call_id"]) not in noticed
            and datetime.fromisoformat(str(event.payload["notice_after"])) <= simulated_at
        ),
        None,
    )
    if missed is None:
        return []
    call_id = str(missed.payload["call_id"])
    caller_id = str(missed.payload["caller_id"])
    notification = DomainEvent(
        "phone.notification_noticed",
        "pathos",
        {"call_id": call_id, "caller_id": caller_id, "simulated_at": simulated_at.isoformat()},
        causation_id=missed.event_id,
        correlation_id=call_id,
    )
    callback = DomainEvent(
        "phone.callback_scheduled",
        "pathos",
        {
            "call_id": call_id,
            "caller_id": caller_id,
            "due_at": (simulated_at + timedelta(hours=2)).isoformat(),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=notification.event_id,
        correlation_id=call_id,
    )
    return [notification, callback]


def complete_answered_call(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    *,
    actor_locations: Mapping[str, str],
    pathos_energy: float,
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
            and (
                not event.payload.get("ends_at")
                or datetime.fromisoformat(str(event.payload["ends_at"])) <= simulated_at
            )
        ),
        None,
    )
    if answered is None:
        return []
    output = [_call_completed(answered, simulated_at)]
    scene_id = answered.payload.get("scene_id")
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
                source_event=output[0],
                decision_key=f"phone-{answered.payload['call_id']}",
            )
        )
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
