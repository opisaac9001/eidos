"""Source-linked household deliveries with attempts, presence, and scene interruption."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.application.interruption_recovery import recover_user_scene
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.scenes import (
    SceneInterruptProposal,
    project_scenes,
    resolve_scene_interruption,
)


def delivery_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    *,
    actor_locations: Mapping[str, str],
    pathos_awake: bool,
    pathos_energy: float,
) -> list[DomainEvent]:
    """Advance one handoff, resolve one due attempt, or schedule one sourced parcel."""
    completion = _complete_handoff(
        history,
        simulated_at,
        actual_revision,
        actor_locations=actor_locations,
        pathos_energy=pathos_energy,
    )
    if completion:
        return completion
    due = _resolve_due_attempt(
        history,
        simulated_at,
        actual_revision,
        actor_locations=actor_locations,
        pathos_awake=pathos_awake,
    )
    if due:
        return due
    handled_sources = {
        str(event.payload["source_event_id"])
        for event in events_of(history, "delivery.scheduled")
        if isinstance(event.payload.get("source_event_id"), str)
    }
    source = next(
        (
            event
            for event in events_of(history, "perception.recorded")
            if event.payload.get("owner") == "pathos"
            and event.payload.get("source_kind") == "world_event"
            and str(event.event_id) not in handled_sources
            and _sample(f"delivery-source-{event.event_id}") < 0.4
        ),
        None,
    )
    if source is None:
        return []
    delivery_id = f"neighborhood-parcel-{str(source.event_id)[:12]}"
    item_name = _item_name(source)
    arrives_at = (simulated_at + timedelta(days=2)).replace(
        hour=11, minute=0, second=0, microsecond=0
    )
    return [
        DomainEvent(
            "delivery.scheduled",
            "pathos",
            {
                "delivery_id": delivery_id,
                "source_event_id": str(source.event_id),
                "object_id": f"parcel-{str(source.event_id)[:12]}",
                "item_name": item_name,
                "arrives_at": arrives_at.isoformat(),
                "attempt": 1,
                "text": f"A neighborhood follow-up parcel was expected: {item_name}.",
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=source.event_id,
            correlation_id=delivery_id,
        )
    ]


def active_delivery(history: Sequence[DomainEvent]) -> str | None:
    """Return the parcel currently waiting at the door, if any."""
    completed = {
        str(event.payload["delivery_id"])
        for event in events_of(history, "delivery.received", "delivery.returned")
    }
    arrived = next(
        (
            event
            for event in reversed(events_of(history, "delivery.arrived"))
            if str(event.payload["delivery_id"]) not in completed
        ),
        None,
    )
    return str(arrived.payload["delivery_id"]) if arrived else None


def _resolve_due_attempt(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    *,
    actor_locations: Mapping[str, str],
    pathos_awake: bool,
) -> list[DomainEvent]:
    resolved = {
        (str(event.payload["delivery_id"]), int(event.payload["attempt"]))
        for event in events_of(history, "delivery.arrived", "delivery.missed")
    }
    due = next(
        (
            event
            for event in events_of(history, "delivery.scheduled", "delivery.redelivery_scheduled")
            if (str(event.payload["delivery_id"]), int(event.payload["attempt"])) not in resolved
            and datetime.fromisoformat(str(event.payload["arrives_at"])) <= simulated_at
        ),
        None,
    )
    if due is None:
        return []
    delivery_id = str(due.payload["delivery_id"])
    attempt = int(due.payload["attempt"])
    if not pathos_awake or actor_locations.get("pathos") != "home":
        missed = DomainEvent(
            "delivery.missed",
            "pathos",
            {
                "delivery_id": delivery_id,
                "attempt": attempt,
                "reason": "No one answered at the apartment.",
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=due.event_id,
            correlation_id=delivery_id,
        )
        if attempt >= 2:
            return [
                missed,
                DomainEvent(
                    "delivery.returned",
                    "pathos",
                    {
                        "delivery_id": delivery_id,
                        "reason": "The parcel was returned after two missed attempts.",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=missed.event_id,
                    correlation_id=delivery_id,
                ),
            ]
        return [
            missed,
            DomainEvent(
                "delivery.redelivery_scheduled",
                "pathos",
                {
                    **dict(due.payload),
                    "attempt": attempt + 1,
                    "arrives_at": (simulated_at + timedelta(days=1))
                    .replace(hour=11, minute=0, second=0, microsecond=0)
                    .isoformat(),
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=missed.event_id,
                correlation_id=delivery_id,
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
    arrived = DomainEvent(
        "delivery.arrived",
        "pathos",
        {
            "delivery_id": delivery_id,
            "attempt": attempt,
            "source_event_id": str(due.payload["source_event_id"]),
            "object_id": str(due.payload["object_id"]),
            "item_name": str(due.payload["item_name"]),
            "scene_id": user_scene.scene_id if user_scene else None,
            "text": f"A courier arrived with {due.payload['item_name']}.",
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=due.event_id,
        correlation_id=delivery_id,
    )
    output = [arrived]
    if user_scene is None:
        return output
    interruption = resolve_scene_interruption(
        SceneInterruptProposal(
            f"delivery-interrupt-{delivery_id}",
            user_scene.scene_id,
            "pathos",
            arrived.event_id,
            actual_revision + 1,
        ),
        state=project_scenes([*history, arrived]),
        history=[*history, arrived],
        actual_revision=actual_revision + 1,
        simulated_at=simulated_at.isoformat(),
    )
    output.extend(interruption.events)
    if interruption.accepted:
        output.append(
            DomainEvent(
                "conversation.message",
                "pathos",
                {
                    "speaker": "system",
                    "text": "A courier arrived; Pathos stepped away to answer the door.",
                    "channel": "live_visit",
                    "scene_id": user_scene.scene_id,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=arrived.event_id,
                correlation_id=user_scene.scene_id,
            )
        )
    return output


def _complete_handoff(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    actual_revision: int,
    *,
    actor_locations: Mapping[str, str],
    pathos_energy: float,
) -> list[DomainEvent]:
    received = {
        str(event.payload["delivery_id"]) for event in events_of(history, "delivery.received")
    }
    arrived = next(
        (
            event
            for event in events_of(history, "delivery.arrived")
            if str(event.payload["delivery_id"]) not in received
            and datetime.fromisoformat(str(event.payload["simulated_at"])) < simulated_at
        ),
        None,
    )
    if arrived is None:
        return []
    delivery_id = str(arrived.payload["delivery_id"])
    received_event = DomainEvent(
        "delivery.received",
        "pathos",
        {
            "delivery_id": delivery_id,
            "object_id": str(arrived.payload["object_id"]),
            "item_name": str(arrived.payload["item_name"]),
            "text": f"Pathos received {arrived.payload['item_name']}.",
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=arrived.event_id,
        correlation_id=delivery_id,
    )
    stock = _stock_profile(str(arrived.payload["item_name"]))
    registered = DomainEvent(
        "object.registered",
        "pathos",
        {
            "object_id": str(arrived.payload["object_id"]),
            "name": str(arrived.payload["item_name"]),
            "owner_id": "pathos",
            "custodian_id": "pathos",
            "location_id": "home",
            "condition": "good",
            **stock,
            "source": "received-neighborhood-delivery",
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=received_event.event_id,
        correlation_id=delivery_id,
    )
    memory = DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": f"I answered the door and received {arrived.payload['item_name']}.",
            "owner": "pathos",
            "category": "object-transfer",
            "source": "delivery-lifecycle",
            "source_event_id": str(received_event.event_id),
            "object_id": str(arrived.payload["object_id"]),
            "location_id": "home",
            "importance": 0.42,
            "confidence": 1.0,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=received_event.event_id,
        correlation_id=delivery_id,
    )
    output = [received_event, registered, memory]
    scene_id = arrived.payload.get("scene_id")
    if isinstance(scene_id, str):
        output.extend(
            recover_user_scene(
                [*history, *output],
                scene_id,
                simulated_at,
                actual_revision + len(output),
                actor_locations=actor_locations,
                pathos_energy=pathos_energy,
                source_event=received_event,
                decision_key=f"delivery-{delivery_id}",
            )
        )
    return output


def _item_name(source: DomainEvent) -> str:
    cue = " ".join(
        str(source.payload.get(key, "")) for key in ("theme", "opportunity", "text")
    ).casefold()
    choices = (
        (("garden", "growing", "seed"), "a packet of locally saved seeds"),
        (("repair", "craft", "mending"), "a small bundle of repair materials"),
        (("reading", "learning", "book"), "a slim secondhand book"),
        (("art", "sketch", "print"), "a packet of drawing paper"),
        (("tea", "hospitality", "cooking"), "a small box of neighborhood tea"),
    )
    return next(
        (name for terms, name in choices if any(term in cue for term in terms)),
        "a neighborhood circular and keepsake",
    )


def _stock_profile(item_name: str) -> dict[str, object]:
    name = item_name.casefold()
    profiles = (
        ("seeds", 6, 2, "portions"),
        ("repair materials", 4, 1, "pieces"),
        ("drawing paper", 12, 3, "sheets"),
        ("tea", 8, 2, "servings"),
    )
    for term, quantity, reorder_at, unit in profiles:
        if term in name:
            return {"quantity": quantity, "reorder_at": reorder_at, "unit": unit}
    return {}


def _sample(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
