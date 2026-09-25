"""His life, told in his own words.

Much of what happens to Patrick is narrated by rules: a friend's news, Mum's Sunday call, a
date, a week away. Those lines are written well, but they're written once, for everyone.
With a real model configured, each hour the newest of those memories are re-told by him
(the ``pathos_voice`` role): same facts, his words, coloured by how he is today.

The rules keep the facts:
- Every name, place and number in the original must survive.
- No new names may appear.
- The length stays close to the original.

A retelling that breaks any of this is dropped and the original stands. The authored line
is kept alongside (``authored_text``), so nothing is lost and replay is unaffected. The
offline stand-in hands the original back unchanged.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import replace
from datetime import datetime
from time import perf_counter
from typing import Mapping, MutableSequence, Sequence
from uuid import uuid4

from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest, ModelResponse

PER_HOUR = 4
VOICED_SOURCES = frozenset(
    {
        "lived-family",
        "lived-friend-life",
        "lived-romance",
        "lived-holiday",
        "lived-calendar",
        "lived-far-friend",
        "lived-falling-out",
        "lived-home",
        "lived-course",
        "lived-work",
        "lived-joke",
        "lived-body",
        "lived-town-issue",
        "lived-sleep",
        "lived-surfaced",
        "lived-season",
    }
)
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text"],
    "properties": {"text": {"type": "string", "maxLength": 500}},
}
_WORD = re.compile(r"[A-Z][a-zA-Z'’-]+|\d[\d,.:%£]*")
# Capitalised words that aren't names: sentence starts are handled separately.
_ORDINARY = frozenset(
    {
        "I",
        "I'm",
        "I've",
        "I'd",
        "I'll",
        "Mum",
        "Dad",
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
        "Christmas",
        "Easter",
        "OK",
        "TV",
    }
)


def _names(text: str) -> set[str]:
    """Names, places and numbers: capitalised words not at a sentence start, and figures."""
    found: set[str] = set()
    for match in _WORD.finditer(text):
        word = match.group(0).rstrip(".,")
        before = text[: match.start()].rstrip()
        sentence_start = not before or before[-1] in ".!?\"'“:"
        if word[0].isdigit() or (not sentence_start and word not in _ORDINARY):
            found.add(word.removesuffix("'s").removesuffix("’s"))
    return found


def keeps_the_facts(original: str, retold: str) -> bool:
    retold = " ".join(retold.split())
    if not 0.5 * len(original) <= len(retold) <= 1.8 * len(original) + 40:
        return False
    if re.search(r"\b(as an ai|language model|here is|here's a|rewritten)\b", retold, re.I):
        return False
    lowered = retold.casefold()
    kept = all(name.casefold() in lowered for name in _names(original))
    invented = {
        name
        for name in _names(retold)
        if name.casefold() not in original.casefold() and not name[0].isdigit()
    }
    new_numbers = {name for name in _names(retold) if name[0].isdigit() and name not in original}
    return kept and not invented and not new_numbers


async def voice_pending(
    pending: MutableSequence[DomainEvent],
    start: int,
    at: datetime,
    gateway: ModelGateway,
    *,
    mood: str,
    recent: Sequence[str] = (),
) -> list[DomainEvent]:
    """Re-tell this hour's narrated memories in his words, in place. Returns traces."""
    targets = [
        index
        for index in range(start, len(pending))
        if pending[index].kind == "memory.recorded"
        and pending[index].payload.get("source") in VOICED_SOURCES
        and not pending[index].payload.get("authored_text")
        and isinstance(pending[index].payload.get("text"), str)
    ][:PER_HOUR]
    traces: list[DomainEvent] = []
    for index in targets:
        memory = pending[index]
        original = str(memory.payload["text"])
        retold, trace = await _retell(original, memory, at, gateway, mood, recent)
        traces.append(trace)
        if retold is None or retold == original:
            continue
        pending[index] = _with_text(memory, retold, original)
        # The event the memory came from often carries the same line; keep them together.
        source = str(memory.payload.get("source_event_id", ""))
        for other in range(start, len(pending)):
            event = pending[other]
            if str(event.event_id) == source and event.payload.get("text") == original:
                pending[other] = _with_text(event, retold, original)
    return traces


async def _retell(
    original: str,
    memory: DomainEvent,
    at: datetime,
    gateway: ModelGateway,
    mood: str,
    recent: Sequence[str],
) -> tuple[str | None, DomainEvent]:
    context = {
        "task": "voice",
        "time": at.isoformat(),
        "original": original,
        "what_kind_of_moment": str(memory.payload.get("category", "")),
        "mood": mood,
        "recently_in_his_words": list(recent)[-3:],
        "permission": (
            "This is something that just happened in Patrick's life, as a plain record. "
            "Re-tell it as he'd put it in his own head today: first person, his understated "
            "British voice, coloured by his mood. Keep every fact: every name, place and number "
            "exactly as given. Add no new people, places, events or numbers. About the same "
            "length. Return only the re-telling."
        ),
    }
    request = ModelRequest(
        capability="pathos_voice",
        task_version="1",
        temperature=0.7,
        max_output_tokens=200,
        output_schema=_SCHEMA,
        messages=(ModelMessage("user", json.dumps(context)),),
    )
    started = perf_counter()
    response: ModelResponse | None = None
    try:
        response = await asyncio.wait_for(gateway.generate(request), timeout=50)
        if response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "Re-telling was incomplete")
        raw = json.loads(response.content)
        retold = " ".join(str(raw.get("text", "")).split()) if isinstance(raw, dict) else ""
        if not keeps_the_facts(original, retold):
            raise ProposalRejected("changed_facts", "A re-telling must keep the facts")
    except (OSError, TimeoutError, TypeError, ValueError, AttributeError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
        return None, _trace("failed", at, started, response, gateway, code)
    return retold, _trace("ok", at, started, response, gateway, None)


def _with_text(event: DomainEvent, text: str, original: str) -> DomainEvent:
    payload: Mapping[str, object] = {**event.payload, "text": text, "authored_text": original}
    return replace(event, payload=payload)


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
            "role": "pathos_voice",
            "status": status,
            "trace_id": str(uuid4()),
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "model": response.resolved_model if response else getattr(gateway, "model", "unknown"),
            "backend": response.backend if response else "unknown",
            "error_code": error_code,
            "simulated_at": at.isoformat(),
        },
    )
