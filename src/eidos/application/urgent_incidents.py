"""Typed responses to urgent public incidents Pathos directly perceives."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.application.interruption_recovery import recover_user_scene
from eidos.domain.events import DomainEvent
from eidos.domain.scenes import (
    SceneInterruptProposal,
    project_scenes,
    resolve_scene_interruption,
)

_URGENT_TERMS = {
    "fault",
    "injured",
    "broken",
    "danger",
    "help",
    "unsafe",
    "fire",
    "lost",
    "accident",
    "emergency",
}


def urgent_incident_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    *,
    actor_locations: Mapping[str, str],
    pathos_energy: float,
    values: Mapping[str, float],
) -> list[DomainEvent]:
    """Complete an active response or decide one newly perceived urgent incident."""
    active = _active_response(history)
    if active is not None:
        due_at = datetime.fromisoformat(str(active.payload["responds_until"]))
        if due_at > simulated_at:
            return []
        return _complete_response(
            history,
            active,
            simulated_at,
            actual_revision,
            actor_locations=actor_locations,
            pathos_energy=pathos_energy,
        )
    handled = {
        str(event.payload["source_perception_id"])
        for event in history
        if event.kind == "incident.attention_decided"
    }
    perception = next(
        (
            event
            for event in reversed(history)
            if event.kind == "perception.recorded"
            and event.payload.get("owner") == "pathos"
            and event.payload.get("source_kind") == "world_event"
            and str(event.event_id) not in handled
            and event.payload.get("simulated_at") == simulated_at.isoformat()
            and _is_urgent(event)
        ),
        None,
    )
    if perception is None:
        return []
    intensity = _bounded(perception.payload.get("intensity", 0.2))
    care = _bounded(values.get("care", 0.5))
    response_score = max(
        0.05, min(0.95, 0.2 + 0.32 * care + 0.23 * pathos_energy + 0.3 * intensity)
    )
    incident_id = f"urgent-{perception.event_id}"
    responds = _sample(incident_id) < response_score
    decision = DomainEvent(
        "incident.attention_decided",
        "pathos",
        {
            "incident_id": incident_id,
            "source_perception_id": str(perception.event_id),
            "decision": "respond" if responds else "decline",
            "decision_energy": pathos_energy,
            "decision_care": care,
            "intensity": intensity,
            "reason": (
                "Pathos judged that the situation needed his attention."
                if responds
                else "Pathos judged that he could not safely or usefully intervene."
            ),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=perception.event_id,
        correlation_id=incident_id,
    )
    if not responds:
        return [
            decision,
            DomainEvent(
                "incident.response_declined",
                "pathos",
                {
                    "incident_id": incident_id,
                    "source_perception_id": str(perception.event_id),
                    "reason": str(decision.payload["reason"]),
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=decision.event_id,
                correlation_id=incident_id,
            ),
        ]
    duration = min(2, max(1, int(perception.payload.get("duration_hours", 1))))
    user_scene = next(
        (
            scene
            for scene in project_scenes(history).scenes.values()
            if scene.status == "active"
            and {scene.initiator_id, scene.partner_id} == {"pathos", "user"}
        ),
        None,
    )
    started = DomainEvent(
        "incident.response_started",
        "pathos",
        {
            "incident_id": incident_id,
            "source_perception_id": str(perception.event_id),
            "description": str(perception.payload.get("text", "A nearby incident")),
            "location_id": str(perception.payload["location_id"]),
            "scene_id": user_scene.scene_id if user_scene else None,
            "responds_until": (simulated_at + timedelta(hours=duration)).isoformat(),
            "text": "Pathos stopped what he was doing to respond to something nearby.",
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=decision.event_id,
        correlation_id=incident_id,
    )
    output = [decision, started]
    if user_scene is None:
        return output
    interrupted = resolve_scene_interruption(
        SceneInterruptProposal(
            f"incident-interrupt-{incident_id}",
            user_scene.scene_id,
            "pathos",
            started.event_id,
            actual_revision + len(output),
        ),
        state=project_scenes([*history, *output]),
        history=[*history, *output],
        actual_revision=actual_revision + len(output),
        simulated_at=simulated_at.isoformat(),
    )
    output.extend(interrupted.events)
    if interrupted.accepted:
        output.append(
            DomainEvent(
                "conversation.message",
                "pathos",
                {
                    "speaker": "system",
                    "text": "Something nearby needed attention; Pathos had to step away.",
                    "channel": "live_visit",
                    "scene_id": user_scene.scene_id,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=started.event_id,
                correlation_id=user_scene.scene_id,
            )
        )
    return output


def active_incident_location(history: Sequence[DomainEvent], simulated_at: datetime) -> str | None:
    """Keep Pathos at a response site until the bounded response interval ends."""
    active = _active_response(history)
    if active is None:
        return None
    if simulated_at > datetime.fromisoformat(str(active.payload["responds_until"])):
        return None
    return str(active.payload["location_id"])


def _complete_response(
    history: Sequence[DomainEvent],
    started: DomainEvent,
    simulated_at: datetime,
    actual_revision: int,
    *,
    actor_locations: Mapping[str, str],
    pathos_energy: float,
) -> list[DomainEvent]:
    incident_id = str(started.payload["incident_id"])
    still_there = actor_locations.get("pathos") == started.payload["location_id"]
    outcome = DomainEvent(
        "incident.response_completed" if still_there else "incident.response_abandoned",
        "pathos",
        {
            "incident_id": incident_id,
            "source_perception_id": str(started.payload["source_perception_id"]),
            "location_id": str(started.payload["location_id"]),
            "reason": (
                "Pathos stayed long enough to offer a bounded practical response."
                if still_there
                else "Pathos left before the response was complete."
            ),
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=started.event_id,
        correlation_id=incident_id,
    )
    memory = DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": (
                f"I stopped to respond when {started.payload['description']}"
                if still_there
                else f"I started to respond, but left before it was resolved: {started.payload['description']}"
            ),
            "owner": "pathos",
            "category": "world-event",
            "source": "urgent-incident-response",
            "source_event_id": str(outcome.event_id),
            "location_id": str(started.payload["location_id"]),
            "importance": 0.72 if still_there else 0.62,
            "confidence": 1.0,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=outcome.event_id,
        correlation_id=incident_id,
    )
    output = [outcome, memory]
    scene_id = started.payload.get("scene_id")
    if isinstance(scene_id, str):
        output.extend(
            recover_user_scene(
                [*history, *output],
                scene_id,
                simulated_at,
                actual_revision + len(output),
                actor_locations=actor_locations,
                pathos_energy=pathos_energy,
                source_event=outcome,
                decision_key=f"incident-{incident_id}",
            )
        )
    return output


def _active_response(history: Sequence[DomainEvent]) -> DomainEvent | None:
    terminal = {
        str(event.payload["incident_id"])
        for event in history
        if event.kind in {"incident.response_completed", "incident.response_abandoned"}
    }
    return next(
        (
            event
            for event in reversed(history)
            if event.kind == "incident.response_started"
            and str(event.payload["incident_id"]) not in terminal
        ),
        None,
    )


def _is_urgent(perception: DomainEvent) -> bool:
    intensity = _bounded(perception.payload.get("intensity", 0.2))
    text = " ".join(
        str(perception.payload.get(key, ""))
        for key in ("event_type", "cause", "opportunity", "text")
    ).casefold()
    return intensity >= 0.4 or any(term in text for term in _URGENT_TERMS)


def _bounded(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _sample(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
