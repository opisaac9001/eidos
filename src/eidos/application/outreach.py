"""Bounded voluntary in-app messages from Pathos to an existing user relationship."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.application.cognition import perform_pathos_reply
from eidos.domain.events import DomainEvent
from eidos.domain.outreach import project_outreach_config
from eidos.domain.scenes import project_scenes
from eidos.ports.model_gateway import ModelGateway


async def outreach_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    gateway: ModelGateway,
    *,
    pathos_awake: bool,
    context: Mapping[str, object],
) -> list[DomainEvent]:
    """Send at most one grounded message per 72 hours during the fixed daytime window."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Outreach time must be timezone-aware")
    config = project_outreach_config(history)
    if not config.enabled or not pathos_awake or simulated_at.hour != 18:
        return []
    messages = [event for event in history if event.kind == "conversation.message"]
    if not any(event.payload.get("speaker") == "you" for event in messages):
        return []
    replied = {
        str(event.payload.get("request_id"))
        for event in messages
        if event.payload.get("speaker") in {"pathos", "system"}
    }
    if any(
        event.payload.get("speaker") == "you"
        and str(event.payload.get("request_id")) not in replied
        for event in messages
    ):
        return []
    if any(
        scene.status in {"active", "paused"}
        and {scene.initiator_id, scene.partner_id} == {"pathos", "user"}
        for scene in project_scenes(history).scenes.values()
    ):
        return []
    prior = next(
        (
            event
            for event in reversed(messages)
            if event.payload.get("channel") == "in_app_outreach"
        ),
        None,
    )
    if prior is not None and simulated_at - _event_time(prior) < timedelta(
        hours=config.minimum_interval_hours
    ):
        return []
    source = next(
        (
            event
            for event in reversed(history)
            if event.kind == "memory.recorded"
            and event.payload.get("owner", "pathos") == "pathos"
            and event.payload.get("category") != "dream"
            and isinstance(event.payload.get("text"), str)
        ),
        None,
    )
    if source is None:
        return []
    request_id = f"outreach-{simulated_at.date().isoformat()}"
    if any(event.payload.get("request_id") == request_id for event in messages):
        return []
    pending = [
        DomainEvent(
            "outreach.considered",
            "pathos",
            {
                "request_id": request_id,
                "source_memory_id": str(source.event_id),
                "simulated_at": simulated_at.isoformat(),
                "channel": "in_app_only",
            },
            causation_id=source.event_id,
            correlation_id=request_id,
        )
    ]
    model_context = {
        **dict(context),
        "message": "",
        "outreach_reason": "Share one ordinary thought because something from the day genuinely brought the user to mind.",
        "source_memory": str(source.payload["text"]),
    }
    text = await perform_pathos_reply(
        gateway, model_context, simulated_at.isoformat(), pending
    )
    if not text:
        return pending
    lowered = text.lower()
    forbidden_pressure = (
        "you haven't been here",
        "you have not been here",
        "i've been waiting for you",
        "i have been waiting for you",
        "i need you",
        "lonely without you",
    )
    if any(phrase in lowered for phrase in forbidden_pressure):
        pending.append(
            DomainEvent(
                "outreach.rejected",
                "pathos",
                {
                    "request_id": request_id,
                    "reason": "Generated outreach used absence, dependency, or guilt pressure.",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=pending[-1].event_id,
                correlation_id=request_id,
            )
        )
        return pending
    pending.append(
        DomainEvent(
            "conversation.message",
            "pathos",
            {
                "text": text,
                "speaker": "pathos",
                "simulated_at": simulated_at.isoformat(),
                "request_id": request_id,
                "delivery_status": "sent",
                "channel": "in_app_outreach",
                "source_memory_id": str(source.event_id),
            },
            causation_id=source.event_id,
            correlation_id=request_id,
        )
    )
    return pending


def _event_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if not isinstance(value, str):
        raise ValueError("Outreach messages need simulated time")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Outreach message time must be timezone-aware")
    return parsed
