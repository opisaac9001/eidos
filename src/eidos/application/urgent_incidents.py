"""Typed responses to urgent public incidents Pathos directly perceives."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.application.interruption_recovery import recover_user_scene
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
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
    location_id = str(perception.payload["location_id"])
    source_world_event_id = str(perception.payload.get("source_event_id", ""))
    participant_ids = sorted(
        {
            str(event.payload["owner"])
            for event in history
            if event.kind == "perception.recorded"
            and event.payload.get("source_event_id") == source_world_event_id
            and event.payload.get("owner") not in {"pathos", "user"}
            and isinstance(event.payload.get("owner"), str)
            and actor_locations.get(str(event.payload["owner"])) == location_id
        }
    )
    participant_ids_value = ",".join(participant_ids)
    resource_id = _matching_resource(history, perception, location_id)
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
            "participant_ids": participant_ids_value,
            "resource_id": resource_id,
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
                    "participant_ids": participant_ids_value,
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
            "location_id": location_id,
            "scene_id": user_scene.scene_id if user_scene else None,
            "participant_ids": participant_ids_value,
            "resource_id": resource_id,
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
    output = [outcome]
    resource_id = started.payload.get("resource_id")
    if still_there and isinstance(resource_id, str):
        output.append(
            DomainEvent(
                "incident.resource_used",
                "pathos",
                {
                    "incident_id": incident_id,
                    "resource_id": resource_id,
                    "location_id": str(started.payload["location_id"]),
                    "reason": "A suitable resource was physically available at the response site.",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=outcome.event_id,
                correlation_id=incident_id,
            )
        )
    participant_ids = started.payload.get("participant_ids", "")
    if isinstance(participant_ids, str):
        for participant_id in filter(None, participant_ids.split(",")):
            shared = DomainEvent(
                "incident.shared_aftermath",
                "pathos",
                {
                    "incident_id": incident_id,
                    "person_id": participant_id,
                    "outcome": "completed" if still_there else "abandoned",
                    "text": (
                        f"Pathos and {participant_id.replace('-', ' ').title()} shared "
                        "the aftermath of the nearby incident."
                    ),
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=outcome.event_id,
                correlation_id=incident_id,
            )
            output.extend(
                (
                    shared,
                    DomainEvent(
                        "relationship.changed",
                        "pathos",
                        {
                            "person_id": participant_id,
                            "evidence_actor_id": "pathos",
                            "familiarity_delta": 0.03,
                            "trust_delta": 0.02 if still_there else 0.0,
                            "tension_delta": 0.0 if still_there else 0.02,
                            "reason": (
                                "They shared a completed response to a nearby incident."
                                if still_there
                                else "They shared an incident that Pathos left unfinished."
                            ),
                            "simulated_at": simulated_at.isoformat(),
                        },
                        causation_id=shared.event_id,
                        correlation_id=incident_id,
                    ),
                )
            )
    output.append(memory)
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


def _matching_resource(
    history: Sequence[DomainEvent], perception: DomainEvent, location_id: str
) -> str | None:
    cue = " ".join(
        str(perception.payload.get(key, ""))
        for key in ("event_type", "cause", "opportunity", "text")
    ).casefold()
    cue_terms = {word for word in cue.replace("_", " ").split() if len(word) > 3}
    candidates = []
    for item in project_planning(list(history)).objects.values():
        if item.location_id != location_id or item.condition != "good":
            continue
        name_terms = {
            word for word in item.name.casefold().replace("-", " ").split() if len(word) > 3
        }
        overlap = len(cue_terms & name_terms)
        practical = int(
            any(term in cue for term in ("fault", "broken", "repair", "unsafe"))
            and any(term in item.name.casefold() for term in ("repair", "tool", "kit"))
        )
        if overlap or practical:
            candidates.append((overlap + practical, item.object_id))
    return max(candidates, default=(0, None))[1]


def _bounded(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _sample(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
