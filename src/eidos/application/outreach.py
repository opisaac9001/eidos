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
    """Allow a recent user-linked thought to prompt bounded daytime outreach."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Outreach time must be timezone-aware")
    config = project_outreach_config(history)
    if (not config.enabled or not pathos_awake
            or simulated_at.hour >= config.quiet_start_hour
            or simulated_at.hour < config.quiet_end_hour):
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
    memories = {
        str(event.event_id): event for event in history
        if event.kind == "memory.recorded"
        and event.payload.get("owner", "pathos") == "pathos"
        and event.payload.get("source") == "user-conversation"
    }
    source = next(
        (
            event
            for event in reversed(history)
            if event.kind == "thought.recorded"
            and str(event.payload.get("source_memory_id")) in memories
            and isinstance(event.payload.get("text"), str)
            and isinstance(event.payload.get("simulated_at"), str)
            and timedelta(0) <= simulated_at - _event_time(event) <= timedelta(minutes=30)
        ),
        None,
    )
    if source is None:
        return []
    request_id = f"outreach-{source.event_id}"
    if any(
        event.kind == "outreach.considered"
        and (event.payload.get("request_id") == request_id
             or event.payload.get("source_thought_id") == str(source.event_id))
        for event in history
    ) or any(event.payload.get("request_id") == request_id for event in messages):
        return []
    pending = [
        DomainEvent(
            "outreach.considered",
            "pathos",
            {
                "request_id": request_id,
                "source_memory_id": source.payload["source_memory_id"],
                "source_thought_id": str(source.event_id),
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
        "outreach_reason": (
            "Decide whether this private thought actually motivates contacting the user. "
            "Merely remembering them is not enough. You may want to share something specific, "
            "ask a genuine question, or invite them to talk or do something in the simulated world. "
            "If there is no meaningful reason to act, return exactly [KEEP_PRIVATE] as the text. "
            "Otherwise write only the natural message you choose to send. Consider recent_dialogue: "
            "do not repeat an invitation, chase an unanswered message, or send the same idea again. "
            "The supplied thought is subjective, not proof of new events. An invitation is only "
            "a proposal: never claim the user agreed, an activity was booked, or a visit began. "
            "Do not claim the user is absent or owes a reply."
        ),
        "source_memory": str(source.payload["text"]),
        "recent_dialogue": [
            {"speaker": event.payload.get("speaker"), "text": event.payload.get("text")}
            for event in messages[-12:]
        ],
    }
    text = await perform_pathos_reply(
        gateway, model_context, simulated_at.isoformat(), pending
    )
    if not text:
        return pending
    if "[keep_private]" in text.lower():
        pending.append(DomainEvent("outreach.kept_private", "pathos", {
            "request_id": request_id,
            "source_thought_id": str(source.event_id),
            "simulated_at": simulated_at.isoformat(),
        }, causation_id=source.event_id, correlation_id=request_id))
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
                "source_memory_id": source.payload["source_memory_id"],
                "source_thought_id": str(source.event_id),
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
