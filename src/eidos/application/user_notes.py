"""What he knows about you: the picture of your life a friend builds from talking.

Each evening, if you talked that day, he thinks back over what you said and may note a few
things about your life in his own words, in the second person ("You start the new job at
the library on Monday"), with something to ask about later ("how the first day went") and
roughly when. Every note must quote something you actually said, so nothing is invented.
Big things (work, family, pets, home) stay with him; smaller details fade after a couple of
months unless you mention them again. When the time comes he asks, in conversation, or,
if you are close and have allowed him to reach out, in a short message of his own.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import perf_counter
from typing import Mapping, Sequence
from uuid import uuid4

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.proposals import ProposalRejected
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest, ModelResponse

REVIEW_HOUR = 21
TOPICS = (
    "work",
    "study",
    "family",
    "friends",
    "health",
    "home",
    "pets",
    "plans",
    "interests",
    "feelings",
    "other",
)
LASTING = frozenset({"work", "study", "family", "pets", "home", "interests"})
FADES_AFTER = timedelta(days=60)
ASK_WINDOW = timedelta(days=14)
MAX_NOTES_A_DAY = 4

_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["notes"],
    "properties": {
        "notes": {
            "type": "array",
            "maxItems": MAX_NOTES_A_DAY,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["topic", "note", "source_quote", "follow_up", "ask_after_days"],
                "properties": {
                    "topic": {"type": "string", "enum": list(TOPICS)},
                    "note": {"type": "string", "maxLength": 160},
                    "source_quote": {"type": "string", "maxLength": 200},
                    "follow_up": {"type": "string", "maxLength": 120},
                    "ask_after_days": {"type": "integer", "minimum": 0, "maximum": 21},
                },
            },
        },
        "running_joke": {
            "type": "object",
            "additionalProperties": False,
            "required": ["label", "source_quote"],
            "properties": {
                "label": {"type": "string", "maxLength": 60},
                "source_quote": {"type": "string", "maxLength": 200},
            },
        },
    },
}
JOKE_GAP = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class Note:
    note_id: str
    topic: str
    text: str
    follow_up: str
    ask_from: datetime
    learned_at: datetime
    asked: bool


def known_about_you(history: Sequence[DomainEvent], at: datetime) -> list[Note]:
    """What he still remembers of your life: the big things, and the recent small ones."""
    asked = {str(e.payload.get("note_id")) for e in events_of(history, "user.note_asked_about")}
    notes: list[Note] = []
    for event in events_of(history, "user.note_learned"):
        payload = event.payload
        learned = datetime.fromisoformat(str(payload["simulated_at"]))
        topic = str(payload.get("topic", "other"))
        if learned > at or (topic not in LASTING and at - learned > FADES_AFTER):
            continue
        notes.append(
            Note(
                str(payload["note_id"]),
                topic,
                str(payload["text"]),
                str(payload.get("follow_up") or ""),
                learned + timedelta(days=int(payload.get("ask_after_days", 0))),
                learned,
                str(payload["note_id"]) in asked,
            )
        )
    return notes


def things_to_ask(history: Sequence[DomainEvent], at: datetime) -> list[Note]:
    """Follow-ups that are due and not yet asked, most recent first."""
    return sorted(
        (
            note
            for note in known_about_you(history, at)
            if note.follow_up
            and not note.asked
            and note.ask_from <= at <= note.ask_from + ASK_WINDOW
        ),
        key=lambda note: note.ask_from,
        reverse=True,
    )


def user_knowledge_context(history: Sequence[DomainEvent], at: datetime) -> dict[str, object]:
    notes = known_about_you(history, at)
    return {
        "what_he_knows_about_you": [note.text for note in notes][-12:],
        "things_to_ask_you_about": [note.follow_up for note in things_to_ask(history, at)][:2],
    }


def asked_about_events(
    history: Sequence[DomainEvent], at: datetime, reply: str
) -> list[DomainEvent]:
    """Record a follow-up as asked when his reply actually asks about it."""
    if "?" not in reply:
        return []
    words = set(re.findall(r"[a-z']{4,}", reply.casefold()))
    for note in things_to_ask(history, at):
        if words & set(re.findall(r"[a-z']{4,}", note.follow_up.casefold())):
            return [
                DomainEvent(
                    "user.note_asked_about",
                    "pathos",
                    {"note_id": note.note_id, "simulated_at": at.isoformat(), "owner": "pathos"},
                    correlation_id=note.note_id,
                )
            ]
    return []


async def user_notes_events(
    history: Sequence[DomainEvent], at: datetime, gateway: ModelGateway
) -> list[DomainEvent]:
    """At the end of a day you talked, note what he learned about your life."""
    if at.hour != REVIEW_HOUR:
        return []
    today = at.date().isoformat()
    if any(
        str(e.payload.get("simulated_at", ""))[:10] == today
        for e in events_of(history, "user.notes_reviewed")
    ):
        return []
    messages = [
        str(e.payload["text"])
        for e in events_of(history, "conversation.message")
        if e.payload.get("speaker") == "you"
        and str(e.payload.get("simulated_at", ""))[:10] == today
        and isinstance(e.payload.get("text"), str)
    ]
    if not messages:
        return []
    known = [note.text for note in known_about_you(history, at)]
    exchange = [
        f"{e.payload.get('speaker')}: {e.payload['text']}"
        for e in events_of(history, "conversation.message")
        if str(e.payload.get("simulated_at", ""))[:10] == today
        and isinstance(e.payload.get("text"), str)
    ]
    context = {
        "task": "notes",
        "time": at.isoformat(),
        "todays_messages": messages[-30:],
        "todays_exchange": exchange[-40:],
        "already_known": known[-20:],
        "permission": (
            "Thinking back over what the user told Patrick today, note up to four things about "
            "their life worth remembering, as short second-person sentences in his words "
            "('You start the new job on Monday'). Only what they actually said: quote the exact "
            "words in source_quote. Skip small talk and anything already known. If something is "
            "coming up, give a natural follow_up ('how the first day went') and ask_after_days; "
            "otherwise follow_up is empty. Return no notes if nothing stands out. Separately, "
            "if one moment in todays_exchange genuinely made you both laugh and could become "
            "a running joke between you, give it a short label ('the otter thing') and quote "
            "the exact words it started with in running_joke; otherwise leave running_joke "
            "out."
        ),
    }
    request = ModelRequest(
        capability="pathos_user_notes",
        task_version="1",
        temperature=0.3,
        max_output_tokens=500,
        output_schema=_OUTPUT_SCHEMA,
        messages=(ModelMessage("user", json.dumps(context)),),
    )
    started = perf_counter()
    response: ModelResponse | None = None
    reviewed = DomainEvent(
        "user.notes_reviewed",
        "pathos",
        {"messages": len(messages), "simulated_at": at.isoformat(), "owner": "pathos"},
    )
    try:
        response = await asyncio.wait_for(gateway.generate(request), timeout=50)
        if response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "Notes proposal was incomplete")
        proposed = json.loads(response.content).get("notes", [])
        if not isinstance(proposed, list):
            raise ProposalRejected("invalid_shape", "Notes must be a list")
    except (OSError, TimeoutError, TypeError, ValueError, AttributeError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
        return [reviewed, _trace("failed", at, started, response, gateway, code)]
    output = [reviewed, _trace("ok", at, started, response, gateway, None)]
    joke = _valid_joke(json.loads(response.content).get("running_joke"), exchange)
    last_joke = [
        e for e in events_of(history, "joke.shared") if e.payload.get("person_id") == "user"
    ]
    if joke and (
        not last_joke
        or at - datetime.fromisoformat(str(last_joke[-1].payload["simulated_at"])) >= JOKE_GAP
    ):
        from eidos.application.in_jokes import user_joke_event

        output.append(user_joke_event(joke[0], joke[1], at, reviewed))
    seen = {text.casefold() for text in known}
    for index, raw in enumerate(proposed[:MAX_NOTES_A_DAY]):
        try:
            note = _valid_note(raw, messages)
        except ProposalRejected:
            continue
        key = str(note["text"]).casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(
            DomainEvent(
                "user.note_learned",
                "pathos",
                {
                    "note_id": f"note-{today}-{index}",
                    **note,
                    "simulated_at": at.isoformat(),
                    "owner": "pathos",
                },
                causation_id=reviewed.event_id,
                correlation_id=f"note-{today}-{index}",
            )
        )
    return output


def _valid_note(raw: object, messages: Sequence[str]) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise ProposalRejected("invalid_note", "A note must be an object")
    topic = str(raw.get("topic", ""))
    text = " ".join(str(raw.get("note", "")).split())
    quote = " ".join(str(raw.get("source_quote", "")).split()).casefold().strip(" .!?\"'")
    follow_up = " ".join(str(raw.get("follow_up", "")).split()).rstrip("?. ")
    days = raw.get("ask_after_days", 0)
    if topic not in TOPICS or not 8 <= len(text) <= 160:
        raise ProposalRejected("invalid_note", "A note needs a topic and a short sentence")
    if not re.match(r"^(you|your|you're|you've)\b", text.casefold()):
        raise ProposalRejected("invalid_note", "Notes are about you, in the second person")
    said = " ".join(" ".join(message.split()) for message in messages).casefold()
    if len(quote) < 4 or quote not in said:
        raise ProposalRejected("ungrounded", "A note must quote what was actually said")
    if isinstance(days, bool) or not isinstance(days, int) or not 0 <= days <= 21:
        raise ProposalRejected("invalid_note", "ask_after_days must be 0 to 21")
    return {
        "topic": topic,
        "text": text,
        "source_quote": quote,
        "follow_up": follow_up,
        "ask_after_days": days if follow_up else 0,
    }


def _valid_joke(raw: object, exchange: Sequence[str]) -> tuple[str, str] | None:
    """A running joke must be short and start from words actually said today."""
    if not isinstance(raw, Mapping):
        return None
    label = " ".join(str(raw.get("label", "")).split())
    quote = " ".join(str(raw.get("source_quote", "")).split()).strip(" .!?\"'")
    said = " ".join(" ".join(line.split()) for line in exchange).casefold()
    if not 3 <= len(label) <= 60 or len(quote) < 4 or quote.casefold() not in said:
        return None
    return label, quote


def _trace(
    status: str,
    at: datetime,
    started: float,
    response: ModelResponse | None,
    gateway: ModelGateway,
    error_code: str | None,
) -> DomainEvent:
    return DomainEvent(
        "role.completed",
        "pathos",
        {
            "role": "pathos_user_notes",
            "status": status,
            "trace_id": str(uuid4()),
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "model": response.resolved_model if response else getattr(gateway, "model", "unknown"),
            "backend": response.backend if response else "unknown",
            "error_code": error_code,
            "simulated_at": at.isoformat(),
        },
    )
