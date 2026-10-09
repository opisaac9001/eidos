"""Daydreams that lead somewhere: two things he remembers, put side by side, now and then
suggest an idea worth keeping.

Ideas often come from putting two unrelated things together and noticing they fit (the
"daydreaming loop" idea: pair memories, let a critic keep the rare good connection). In
the small hours, while he sleeps and the bigger model is idle, a recent memory is paired
with an older one or one of his interests, the model looks for a small, specific idea that
connects them, and the rules keep it only if it's concrete, new and something he could
actually do. A kept idea becomes something he means to do, and a memory of having had it.
Most nights there's nothing, which is how it should be.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.application.bookings import remember
from eidos.application.memory_life import is_routine_note
from eidos.application.open_loops import FORMED, intended, open_loops
from eidos.domain.british import british
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest

IDEA = "idea.had"
LET_GO = "idea.let_go"
HOUR = 2
_INTERESTS = (
    "his film camera",
    "his record player and the records he likes",
    "tuning his block plane and practising on offcuts",
    "slow filter coffee",
    "vegetarian cooking",
    "walking by the River Alder",
    "the repair workshop and the things people bring in",
    "the interactive fiction game he keeps tinkering with",
    "an essay he means to write about technology and ethics",
    "the freelance work he's got on",
)
_KINDS = {"project", "photo", "tell_someone", "try", "make", "question"}
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["idea", "kind", "worth"],
    "properties": {
        "idea": {"type": "string", "maxLength": 240},
        "kind": {"type": "string", "maxLength": 20},
        "worth": {"type": "integer", "minimum": 1, "maximum": 5},
    },
}
_VAGUE = re.compile(r"\b(something|somehow|maybe one day|explore|reflect on|think about)\b", re.I)
_WORD = re.compile(r"[a-z']+")


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _when(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return None


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.casefold()) if len(w) >= 4}


def _could(idea: str) -> str | None:
    """'I could photograph the bench' -> 'photograph the bench'."""
    match = re.match(r"^\s*i (?:could|might|want to|ought to)\s+(.+?)[.!]?$", idea, re.IGNORECASE)
    if match is None or len(_words(match.group(1))) < 2:
        return None
    rest = match.group(1).strip()
    return rest[0].lower() + rest[1:]


def _pair(history: Sequence[DomainEvent], at: datetime) -> tuple[str, str] | None:
    """A recent memory that mattered, and an older one or one of his interests."""
    mine = [
        e
        for e in events_of(history, "memory.recorded")[-600:]
        if e.payload.get("owner", "pathos") == "pathos"
        and e.payload.get("category") != "dream"
        and not is_routine_note(str(e.payload.get("text", "")))
        and float(e.payload.get("importance", 0.3) or 0.3) >= 0.45
    ]
    recent = [e for e in mine if (w := _when(e)) and at - w <= timedelta(days=3)]
    older = [e for e in mine if (w := _when(e)) and at - w > timedelta(days=7)]
    if not recent:
        return None
    night = at.date().isoformat()
    first = recent[int(_roll("recent", night) * len(recent))]
    if older and _roll("which", night) < 0.5:
        second = str(older[int(_roll("older", night) * len(older))].payload.get("text", ""))
    else:
        second = _INTERESTS[int(_roll("interest", night) * len(_INTERESTS))]
    return str(first.payload.get("text", "")), second


async def daydream_events(
    history: Sequence[DomainEvent], at: datetime, gateway: ModelGateway, *, asleep: bool
) -> list[DomainEvent]:
    """Most nights nothing; now and then an idea worth keeping."""
    if not asleep or at.hour != HOUR or _roll("tonight", at.date().isoformat()) >= 0.5:
        return []
    if any(
        (w := _when(e)) and at - w < timedelta(hours=20)
        for e in events_of(history, IDEA, LET_GO)[-3:]
    ):
        return []
    pair = _pair(history, at)
    if pair is None:
        return []
    first, second = pair
    request = ModelRequest(
        capability="pathos_daydream",
        task_version="1",
        temperature=0.9,
        max_output_tokens=160,
        output_schema=_SCHEMA,
        messages=(
            ModelMessage(
                "user",
                json.dumps(
                    {
                        "task": "daydream",
                        "one_thing": first,
                        "another_thing": second,
                        "permission": (
                            "Put these two things from Patrick's life side by side. Is there one "
                            "small, specific idea that connects them, something he could actually "
                            "do (a photo to take, a thing to make or try, something to tell or "
                            "ask someone, a small project)? Write it as he'd think it, first "
                            "person, starting 'I could' or 'I should'. kind is one of project, "
                            "photo, tell_someone, try, make, question. worth is 1 to 5: how good "
                            "an idea it honestly is; most connections are a 1 or 2. Invent no "
                            "people, places or events."
                        ),
                    }
                ),
            ),
        ),
    )
    try:
        response = await gateway.generate(request)
        raw = json.loads(response.content)
        idea = british(" ".join(str(raw.get("idea", "")).split()))
        kind = str(raw.get("kind", ""))
        worth = int(raw.get("worth", 0))
    except (OSError, TimeoutError, TypeError, ValueError, AttributeError):
        return []
    # The critic: concrete, new, doable, and honestly worth it.
    meant = intended(idea) or _could(idea)
    why_not = (
        "not good enough"
        if worth < 4
        else "not something he could do"
        if kind not in _KINDS or meant is None
        else "too vague"
        if _VAGUE.search(idea)
        else "he's already meaning to"
        if any(
            len(_words(loop.text) & _words(meant or "")) >= max(2, len(_words(meant or "")) // 2)
            for loop in open_loops(history)
        )
        else None
    )
    if why_not is not None:
        # Let go, but kept on record so the critic can be checked.
        return [
            DomainEvent(
                LET_GO,
                "pathos",
                {
                    "idea": idea[:240],
                    "worth": worth,
                    "reason": why_not,
                    "simulated_at": at.isoformat(),
                },
            )
        ]
    had = DomainEvent(
        IDEA,
        "pathos",
        {
            "idea": idea,
            "kind": kind,
            "worth": worth,
            "from_one": first[:160],
            "from_another": second[:160],
            "simulated_at": at.isoformat(),
        },
    )
    return [
        had,
        remember(
            had, f"Had an idea: {idea}", at, 0.5, origin="lived-daydream", category="experience"
        ),
        DomainEvent(
            FORMED,
            "pathos",
            {
                "intention_id": f"loop:{had.event_id}",
                "text": meant,
                "importance": 0.5,
                "source": "idea",
                "source_event_id": str(had.event_id),
                "simulated_at": at.isoformat(),
            },
            causation_id=had.event_id,
        ),
    ]
