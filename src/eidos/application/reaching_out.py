"""Reaching out: Patrick texts someone he's been thinking about, and they reply in time.

His passing thoughts can turn into wanting to get in touch: Rowan's mum is ill, Beth is
leaving for Bristol. When that pull is strong and the moment is right, he sends a short
text in his own words (the ``pathos_text`` role), and the person answers a while later in
theirs, written as one line of a scene from their side. Their reply becomes a memory, so
it's there for his next thoughts.

The rules keep it human:
- No texting late at night or first thing.
- Not the same person twice in a day.
- Only a few people a day.
- Not someone he's with right now.

Not everyone replies quickly, and now and then someone doesn't reply at all.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta
from hashlib import sha256
from time import perf_counter
from typing import Callable, Collection, Mapping, Sequence
from uuid import uuid4

from eidos.application.bookings import remember
from eidos.application.cognition import perform
from eidos.application.friends_lives import friends_lives_context
from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest

REACHED = "contact.reached_out"
REPLIED = "contact.reply_received"
UNANSWERED = "contact.went_unanswered"
TEXT_FROM_HOUR, TEXT_UNTIL_HOUR = 8, 22
SAME_PERSON_GAP = timedelta(hours=20)
PER_DAY = 3
NO_REPLY_CHANCE = 0.12
GIVE_UP_AFTER = timedelta(hours=8)
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text"],
    "properties": {"text": {"type": "string", "maxLength": 300}},
}


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _at(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return None


def why_not(
    history: Sequence[DomainEvent],
    at: datetime,
    person_id: str,
    with_him: Collection[str] = (),
) -> str | None:
    """The reason he wouldn't text this person now, or None if he might."""
    if not TEXT_FROM_HOUR <= at.hour < TEXT_UNTIL_HOUR:
        return "too late or too early to text"
    if person_id in with_him:
        return "they're right here"
    today = 0
    for event in reversed(history):
        if event.kind != REACHED:
            continue
        when = _at(event)
        if when is None:
            continue
        if event.payload.get("person_id") == person_id and at - when < SAME_PERSON_GAP:
            return "already texted them today"
        if when.date() == at.date():
            today += 1
        if at - when > timedelta(days=1):
            break
    if today >= PER_DAY:
        return "has texted enough people today"
    return None


async def reach_out_events(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    *,
    person_id: str,
    person_name: str,
    who_they_are: str,
    on_his_mind: Sequence[str],
    mood: str,
    with_him: Collection[str] = (),
    cause: DomainEvent | None = None,
) -> list[DomainEvent]:
    """He texts someone he's been thinking about; empty if now isn't the moment."""
    if why_not(history, at, person_id, with_him) is not None:
        return []
    context = {
        "task": "text",
        "time": at.isoformat(),
        "to": person_name,
        "who_they_are": who_they_are,
        "on_his_mind": [str(thought) for thought in on_his_mind][-3:],
        "what_he_knows_of_their_life": [
            item["what"]
            for item in friends_lives_context(history, at, {person_id: person_name})
            if item["who"] == person_name
        ][:3],
        "mood": mood,
        "permission": (
            f"Patrick has been thinking about {person_name} and decides to text them. Write "
            "the text he sends: one to three short lines, casual and British, the way he'd "
            "really text a friend. Ground it in what's on his mind; don't invent news, plans "
            "or events. No sign-off, no emoji unless it's natural. Return only the text."
        ),
    }
    request = ModelRequest(
        capability="pathos_text",
        task_version="1",
        temperature=0.7,
        max_output_tokens=120,
        output_schema=_SCHEMA,
        messages=(ModelMessage("user", json.dumps(context)),),
    )
    started = perf_counter()
    try:
        response = await asyncio.wait_for(gateway.generate(request), timeout=50)
        if response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "The text was cut off")
        raw = json.loads(response.content)
        text = " ".join(str(raw.get("text", "")).split()) if isinstance(raw, dict) else ""
        words = len(text.split())
        if not 2 <= words <= 60 or re.search(r"\b(as an ai|language model)\b", text, re.I):
            raise ProposalRejected("not_a_text", "That isn't a text he'd send")
    except (OSError, TimeoutError, TypeError, ValueError, AttributeError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
        return [_trace("failed", at, started, None, gateway, code)]
    contact_id = str(uuid4())
    replies = _roll("reply", contact_id) >= NO_REPLY_CHANCE
    delay = timedelta(minutes=10 + int(_roll("delay", contact_id) * 140))
    sent = DomainEvent(
        REACHED,
        "pathos",
        {
            "contact_id": contact_id,
            "person_id": person_id,
            "person_name": person_name,
            "channel": "text",
            "text": text,
            "reply_due_at": (at + delay).isoformat() if replies else "",
            "simulated_at": at.isoformat(),
        },
        causation_id=cause.event_id if cause is not None else None,
        correlation_id=contact_id,
    )
    return [
        _trace("ok", at, started, response, gateway, None),
        sent,
        remember(
            sent,
            f"I texted {person_name}: “{text}”",
            at,
            0.5,
            origin="lived-reaching-out",
            person_id=person_id,
        ),
    ]


async def reply_events(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    whereabouts: Callable[[str], Mapping[str, object]] | None = None,
) -> list[DomainEvent]:
    """Replies that have come in by now, written from the other person's side.

    ``whereabouts`` says where someone is and what they're doing, so a reply fits it: Ellis
    wrote "Morning, just woke up" while at the workshop with Patrick.
    """
    settled = {
        str(event.payload.get("contact_id"))
        for event in history
        if event.kind in {REPLIED, UNANSWERED}
    }
    output: list[DomainEvent] = []
    for sent in [event for event in history if event.kind == REACHED][-12:]:
        contact_id = str(sent.payload.get("contact_id"))
        if contact_id in settled:
            continue
        sent_at = _at(sent)
        due_raw = str(sent.payload.get("reply_due_at") or "")
        name = str(sent.payload.get("person_name", "They"))
        if sent_at is None:
            continue
        if not due_raw:
            if at - sent_at >= GIVE_UP_AFTER:
                output.append(_unanswered(sent, at))
            continue
        if datetime.fromisoformat(due_raw) > at:
            continue
        pending: list[DomainEvent] = []
        person_id = str(sent.payload.get("person_id") or "")
        # What's really going on in their life, so the reply fits it and invents nothing.
        their_life = [
            item["what"]
            for item in friends_lives_context(history, at, {person_id: name})
            if item["who"] == name
        ][:3]
        right_now = dict(whereabouts(person_id)) if whereabouts and person_id else {}
        in_person = bool(right_now.get("with_patrick"))
        reply = await perform(
            gateway,
            "firmament",
            {
                "time": at.isoformat(),
                "location": (
                    f"in person, {right_now.get('where_they_are')}"
                    if in_person
                    else "by text message"
                ),
                "person": name,
                "scene_mode": True,
                "scene_speaker": name,
                "scene_audience": "Pathos",
                "scene_topic": f"replying to his text: {sent.payload.get('text', '')}",
                "prior_turns": [{"speaker": "Pathos", "text": sent.payload.get("text", "")}],
                "personal_relationship_context": {
                    "what_is_going_on_in_their_life": their_life,
                    "right_now": right_now,
                    "instruction": (
                        f"Reply as {name} would"
                        + (", in person, since they're with him now" if in_person else " by text")
                        + ": short and natural, answering only what his text actually said, "
                        "from where they are and what they're doing right now. What's going on "
                        "in their life is true; they may mention it. Invent nothing else: no "
                        "news, plans, visits or promises, and don't offer to come round or "
                        "bring anything."
                    ),
                },
            },
            at.isoformat(),
            pending,
        )
        output.extend(event for event in pending if event.kind == "role.completed")
        if reply is None:
            if at - sent_at >= GIVE_UP_AFTER:
                output.append(_unanswered(sent, at))
            continue
        received = DomainEvent(
            REPLIED,
            "pathos",
            {
                "contact_id": contact_id,
                "person_id": sent.payload.get("person_id"),
                "person_name": name,
                "text": reply,
                "simulated_at": at.isoformat(),
            },
            causation_id=sent.event_id,
            correlation_id=contact_id,
        )
        output.extend(
            [
                received,
                remember(
                    received,
                    f"{name} answered my text in person: “{reply}”"
                    if in_person
                    else f"{name} texted back: “{reply}”",
                    at,
                    0.55,
                    origin="lived-reaching-out",
                    person_id=str(sent.payload.get("person_id") or "") or None,
                ),
            ]
        )
    return output


def _unanswered(sent: DomainEvent, at: datetime) -> DomainEvent:
    return DomainEvent(
        UNANSWERED,
        "pathos",
        {"contact_id": sent.payload.get("contact_id"), "simulated_at": at.isoformat()},
        causation_id=sent.event_id,
        correlation_id=str(sent.payload.get("contact_id")),
    )


def _trace(
    status: str,
    at: datetime,
    started: float,
    response: object,
    gateway: ModelGateway,
    error_code: str | None,
) -> DomainEvent:
    return DomainEvent(
        "role.completed",
        "pathos",
        {
            "role": "pathos_text",
            "status": status,
            "trace_id": str(uuid4()),
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "model": getattr(response, "resolved_model", None)
            or getattr(gateway, "model", "unknown"),
            "backend": getattr(response, "backend", None) or "unknown",
            "error_code": error_code,
            "simulated_at": at.isoformat(),
        },
    )


def texts_view(history: Sequence[DomainEvent], limit: int = 10) -> list[dict[str, object]]:
    """His recent texts with friends, and what came back, for the page and his context."""
    replies = {
        str(event.payload.get("contact_id")): event for event in history if event.kind == REPLIED
    }
    output: list[dict[str, object]] = []
    for sent in [event for event in history if event.kind == REACHED][-limit:]:
        reply = replies.get(str(sent.payload.get("contact_id")))
        output.append(
            {
                "to": sent.payload.get("person_name"),
                "at": sent.payload.get("simulated_at"),
                "he_wrote": sent.payload.get("text"),
                "they_replied": reply.payload.get("text") if reply else None,
            }
        )
    return list(reversed(output))
