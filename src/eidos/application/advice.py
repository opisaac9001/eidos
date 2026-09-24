"""Asking you what you think: bringing the big questions in his life to a friend.

When something in his life needs deciding, and you're a friend (or have talked with him on
a few days), he wants your view:
- Ellis asking if he'd take the workshop on one day;
- whether to move flat;
- whether to message a friend he's fallen out with;
- whether to say something to someone he likes.

He brings it up when you next talk (``wants_your_view_on`` in the conversation context),
or, if you've allowed him to reach out, in a short message of his own.

Each evening he thinks back over what you said since he asked, and notes whether you leaned
for or against, quoting your own words (the ``pathos_advice_heard`` role; nothing is
invented). Your view then weighs in when he decides: one voice among his own values, never
a command. He may still do the opposite, and if he takes your advice, he says so.
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

WANTED = "advice.wanted"
HEARD = "advice.heard"
REVIEW_HOUR = 21
LEANS = ("for", "against", "unsure", "none")
LISTENS_FOR = timedelta(days=21)

_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["leans", "source_quote"],
    "properties": {
        "leans": {"type": "string", "enum": list(LEANS)},
        "source_quote": {"type": "string", "maxLength": 200},
    },
}


@dataclass(frozen=True, slots=True)
class Decision:
    decision_id: str
    question: str
    about: str


def open_decisions(history: Sequence[DomainEvent], names: Mapping[str, str]) -> list[Decision]:
    """The things in his life that are waiting on a decision right now."""
    from eidos.application.falling_out import _open as open_rifts
    from eidos.application.romance import current_arc

    decisions: list[Decision] = []
    steps = {str(e.payload.get("step")) for e in events_of(history, "work.arc_step")}
    if "future" in steps and "answer" not in steps:
        decisions.append(
            Decision(
                "workshop",
                "Ellis asked if I'd ever think about taking the workshop on when he retires. "
                "I can't decide. What would you do?",
                "whether to take on the workshop",
            )
        )
    moves = events_of(history, "home.move")
    if (
        moves
        and moves[-1].payload.get("stage") == "looking"
        and not moves[-1].payload.get("partner_id")
    ):
        decisions.append(
            Decision(
                f"move-{moves[-1].payload['move_id']}",
                "I'm thinking about moving flat. Mine's fine, really. Is that mad, or about time?",
                "whether to move flat",
            )
        )
    for person, (fell_out, _, _) in sorted(open_rifts(history).items()):
        name = names.get(person, person.replace("-", " ").title()).split()[0]
        decisions.append(
            Decision(
                f"rift-{person}-{fell_out.date().isoformat()}",
                f"I fell out with {name}. Should I message them, or give it time?",
                f"whether to reach out to {name} after falling out",
            )
        )
    arc = current_arc(history)
    if arc is not None and arc[1] == "drawn":
        name = names.get(arc[0], arc[0].replace("-", " ").title()).split()[0]
        decisions.append(
            Decision(
                f"crush-{arc[0]}",
                f"Can I ask you something? There's someone, {name}. Should I say something, "
                "or am I being daft?",
                f"whether to ask {name} out",
            )
        )
    return decisions


def advice_wanted_events(
    history: Sequence[DomainEvent], at: datetime, names: Mapping[str, str]
) -> list[DomainEvent]:
    """Mark a new question as one he'd like your view on, if you're someone he'd ask."""
    if not _would_ask_you(history):
        return []
    wanted = {str(e.payload["decision_id"]) for e in events_of(history, WANTED)}
    for decision in open_decisions(history, names):
        if decision.decision_id in wanted:
            continue
        return [
            DomainEvent(
                WANTED,
                "pathos",
                {
                    "decision_id": decision.decision_id,
                    "question": decision.question,
                    "about": decision.about,
                    "simulated_at": at.isoformat(),
                    "owner": "pathos",
                },
                correlation_id=f"advice-{decision.decision_id}",
            )
        ]
    return []


def _would_ask_you(history: Sequence[DomainEvent]) -> bool:
    from eidos.application.bonds import FRIENDLY, current_bonds

    if current_bonds(history).get("user") in FRIENDLY:
        return True
    days = {
        str(e.payload.get("simulated_at", ""))[:10]
        for e in events_of(history, "conversation.message")
        if e.payload.get("speaker") == "you"
    }
    return len(days) >= 3


def waiting_for_your_view(
    history: Sequence[DomainEvent], names: Mapping[str, str]
) -> list[DomainEvent]:
    """Questions he has wanted your view on, still open and not yet answered."""
    heard = {str(e.payload["decision_id"]) for e in events_of(history, HEARD)}
    still_open = {d.decision_id for d in open_decisions(history, names)}
    return [
        event
        for event in events_of(history, WANTED)
        if str(event.payload["decision_id"]) in still_open
        and str(event.payload["decision_id"]) not in heard
    ]


def advice_names(history: Sequence[DomainEvent]) -> dict[str, str]:
    from eidos.domain.townsfolk import project_townsfolk
    from eidos.domain.world_catalog import project_world_catalog

    return {
        **project_townsfolk(history).names(),
        **{
            person.person_id: person.name
            for person in project_world_catalog(history).people.values()
        },
    }


ASK_AGAIN_AFTER = timedelta(days=3)


def advice_asked_events(
    history: Sequence[DomainEvent], at: datetime, reply: str, names: Mapping[str, str]
) -> list[DomainEvent]:
    """Note when his reply actually put the question to you, so he doesn't keep asking."""
    if "?" not in reply:
        return []
    words = set(re.findall(r"[a-z']{4,}", reply.casefold()))
    for wanted in waiting_for_your_view(history, names):
        question = set(re.findall(r"[a-z']{4,}", str(wanted.payload["question"]).casefold()))
        if len(words & question) >= 3:
            return [
                DomainEvent(
                    "advice.asked",
                    "pathos",
                    {
                        "decision_id": wanted.payload["decision_id"],
                        "simulated_at": at.isoformat(),
                        "owner": "pathos",
                    },
                    causation_id=wanted.event_id,
                    correlation_id=wanted.correlation_id,
                )
            ]
    return []


def advice_context(
    history: Sequence[DomainEvent], at: datetime, names: Mapping[str, str]
) -> dict[str, object]:
    recently_asked = {
        str(e.payload["decision_id"])
        for e in events_of(history, "advice.asked")
        if at - datetime.fromisoformat(str(e.payload["simulated_at"])) < ASK_AGAIN_AFTER
    }
    waiting = [
        e
        for e in waiting_for_your_view(history, names)
        if str(e.payload["decision_id"]) not in recently_asked
    ]
    heard = events_of(history, HEARD)[-3:]
    return {
        "wants_your_view_on": str(waiting[-1].payload["question"]) if waiting else None,
        "what_you_advised_lately": [
            f'On {e.payload["about"]}, you said: "{e.payload["source_quote"]}"'
            for e in heard
            if at - datetime.fromisoformat(str(e.payload["simulated_at"])) <= timedelta(days=90)
        ],
    }


def advice_on(history: Sequence[DomainEvent], decision_id: str) -> str | None:
    """Which way you leaned on this, if you said: 'for', 'against' or 'unsure'."""
    for event in reversed(events_of(history, HEARD)):
        if event.payload.get("decision_id") == decision_id:
            return str(event.payload["leans"])
    return None


def advice_note(history: Sequence[DomainEvent], decision_id: str, went_with: bool) -> str:
    """A line for his memory of deciding, if you had a view."""
    leaned = advice_on(history, decision_id)
    if leaned not in {"for", "against"}:
        return ""
    return (
        " I kept thinking about what you said, and in the end I did what you'd have done."
        if went_with
        else " I know you'd have gone the other way. I thought about it, honestly I did."
    )


async def advice_heard_events(
    history: Sequence[DomainEvent], at: datetime, gateway: ModelGateway, names: Mapping[str, str]
) -> list[DomainEvent]:
    """In the evening: did you give him a view on what he asked? Which way?"""
    if at.hour != REVIEW_HOUR:
        return []
    output: list[DomainEvent] = []
    for wanted in waiting_for_your_view(history, names):
        asked_at = datetime.fromisoformat(str(wanted.payload["simulated_at"]))
        if at - asked_at > LISTENS_FOR:
            continue
        messages = [
            str(e.payload["text"])
            for e in events_of(history, "conversation.message")
            if e.payload.get("speaker") == "you"
            and isinstance(e.payload.get("text"), str)
            and asked_at <= datetime.fromisoformat(str(e.payload["simulated_at"])) <= at
        ]
        reviewed_today = any(
            e.payload.get("decision_id") == wanted.payload["decision_id"]
            and str(e.payload.get("simulated_at", ""))[:10] == at.date().isoformat()
            for e in events_of(history, "advice.reviewed")
        )
        if not messages or reviewed_today:
            continue
        output += await _review(wanted, messages, at, gateway)
        break  # one question a night is plenty
    return output


async def _review(
    wanted: DomainEvent, messages: Sequence[str], at: datetime, gateway: ModelGateway
) -> list[DomainEvent]:
    decision_id = str(wanted.payload["decision_id"])
    reviewed = DomainEvent(
        "advice.reviewed",
        "pathos",
        {"decision_id": decision_id, "simulated_at": at.isoformat(), "owner": "pathos"},
        causation_id=wanted.event_id,
    )
    context = {
        "task": "advice",
        "time": at.isoformat(),
        "question": str(wanted.payload["question"]),
        "messages_since": list(messages[-30:]),
        "permission": (
            "Patrick asked the user this question about his life. Reading what the user has "
            "said since, did they give a view? leans is 'for' if they encouraged him to do it, "
            "'against' if they advised not to or to wait, 'unsure' if they engaged but didn't "
            "lean, and 'none' if they didn't address it. Quote their exact words in "
            "source_quote (empty for none)."
        ),
    }
    request = ModelRequest(
        capability="pathos_advice_heard",
        task_version="1",
        temperature=0.1,
        max_output_tokens=200,
        output_schema=_OUTPUT_SCHEMA,
        messages=(ModelMessage("user", json.dumps(context)),),
    )
    started = perf_counter()
    response: ModelResponse | None = None
    try:
        response = await asyncio.wait_for(gateway.generate(request), timeout=50)
        if response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "Advice reading was incomplete")
        raw = json.loads(response.content)
        leans, quote = _valid(raw, messages)
    except (OSError, TimeoutError, TypeError, ValueError, AttributeError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
        return [reviewed, _trace("failed", at, started, response, gateway, code)]
    output = [reviewed, _trace("ok", at, started, response, gateway, None)]
    if leans == "none":
        return output
    heard = DomainEvent(
        HEARD,
        "pathos",
        {
            "decision_id": decision_id,
            "about": str(wanted.payload["about"]),
            "leans": leans,
            "source_quote": quote,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        causation_id=wanted.event_id,
        correlation_id=wanted.correlation_id,
    )
    return [*output, heard]


def _valid(raw: object, messages: Sequence[str]) -> tuple[str, str]:
    if not isinstance(raw, Mapping):
        raise ProposalRejected("invalid_shape", "Advice must be an object")
    leans = str(raw.get("leans", ""))
    if leans not in LEANS:
        raise ProposalRejected("invalid_leans", "Unknown leaning")
    quote = " ".join(str(raw.get("source_quote", "")).split()).strip(" .!?\"'")
    if leans == "none":
        return leans, ""
    said = " ".join(" ".join(message.split()) for message in messages).casefold()
    if len(quote) < 3 or quote.casefold() not in said:
        raise ProposalRejected("ungrounded", "Advice must quote what was actually said")
    return leans, quote


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
            "role": "pathos_advice_heard",
            "status": status,
            "trace_id": str(uuid4()),
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "model": response.resolved_model if response else getattr(gateway, "model", "unknown"),
            "backend": response.backend if response else "unknown",
            "error_code": error_code,
            "simulated_at": at.isoformat(),
        },
    )
