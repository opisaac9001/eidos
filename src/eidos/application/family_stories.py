"""New chapters in his family's lives, written on the fly once the authored ones run out.

His family's authored storylines last about a year. After that, Firmament writes a new short
storyline for whoever's life has gone quiet: two to four steps he will hear about over the
following weeks, in the same understated register ("Dad's joined a clock-repair club and is
insufferable about it"). The rules keep it ordinary: short steps about the relative's own
life, no tragedies or diagnoses, nothing about what Patrick did. At most one storyline a
week, and only for someone whose stories have all been heard.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from time import perf_counter
from typing import Sequence
from uuid import uuid4

from eidos.application.family import FAMILY, NEWS, stories_run_out
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.proposals import ProposalRejected
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest, ModelResponse

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["steps"],
    "properties": {
        "steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {"type": "string", "maxLength": 180},
        }
    },
}
_TOO_HEAVY = re.compile(
    r"\b(died|dies|death|dead|funeral|cancer|terminal|tumou?r|divorce|affair|arrested|"
    r"hospice|stroke|heart attack)\b",
    re.IGNORECASE,
)


async def family_storyline_events(
    history: Sequence[DomainEvent], at: datetime, gateway: ModelGateway
) -> list[DomainEvent]:
    """On a Sunday morning, a new storyline for someone whose life has gone quiet."""
    if at.weekday() != 6 or at.hour != 11:
        return []
    week = at.isocalendar()
    if any(
        e.payload.get("week") == f"{week.year}-W{week.week:02d}"
        for e in events_of(history, "family.storyline_written")
    ):
        return []
    person_id = next((p for p in FAMILY if stories_run_out(history, p)), None)
    if person_id is None:
        return []
    relative = FAMILY[person_id]
    heard = [
        str(e.payload["text"])
        for e in events_of(history, "family.news")
        if e.payload.get("person_id") == person_id
    ]
    context = {
        "task": "family_storyline",
        "time": at.isoformat(),
        "relative": {"called": relative.called, "name": relative.name, "about": relative.about},
        "what_he_has_heard_lately": heard[-8:],
        "permission": (
            f"Write the next small storyline in {relative.called}'s own ordinary life, as 2-4 "
            "short steps Patrick will hear about over the coming weeks, each one sentence in his "
            f"understated voice and about {relative.called}, e.g. "
            f"'{NEWS[person_id][0][0]}'. Ordinary things only: no deaths, diagnoses, "
            "break-ups or crises, and nothing Patrick did."
        ),
    }
    request = ModelRequest(
        capability="firmament_family",
        task_version="1",
        temperature=0.9,
        max_output_tokens=400,
        output_schema=_SCHEMA,
        messages=(ModelMessage("user", json.dumps(context)),),
    )
    started = perf_counter()
    response: ModelResponse | None = None
    try:
        response = await asyncio.wait_for(gateway.generate(request), timeout=50)
        if response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "Storyline was incomplete")
        steps = _valid_steps(json.loads(response.content).get("steps"), relative.called)
    except (OSError, TimeoutError, TypeError, ValueError, AttributeError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
        return [_trace("failed", at, started, response, gateway, code)]
    written = sum(
        1
        for e in events_of(history, "family.storyline_written")
        if e.payload.get("person_id") == person_id
    )
    story_id = f"{person_id}-w{written + 1}"
    return [
        _trace("ok", at, started, response, gateway, None),
        DomainEvent(
            "family.storyline_written",
            "pathos",
            {
                "person_id": person_id,
                "story_id": story_id,
                "step_count": len(steps),
                **{f"step_{index}": step for index, step in enumerate(steps, 1)},
                "week": f"{week.year}-W{week.week:02d}",
                "simulated_at": at.isoformat(),
                "owner": "world",
            },
            correlation_id=story_id,
        ),
    ]


def _valid_steps(raw: object, called: str) -> list[str]:
    if not isinstance(raw, list) or not 1 <= len(raw) <= 4:
        raise ProposalRejected("invalid_shape", "A storyline is one to four steps")
    steps = [" ".join(str(step).split()) for step in raw]
    for step in steps:
        if not 12 <= len(step) <= 180:
            raise ProposalRejected("invalid_step", "Each step is one short sentence")
        if _TOO_HEAVY.search(step):
            raise ProposalRejected("too_heavy", "Family storylines stay ordinary")
        if re.search(r"\b(I|I'm|I've|me)\b", step) and called not in step:
            raise ProposalRejected("about_patrick", "A storyline is about their life")
    if not any(called in step or called.lower() in step.lower() for step in steps):
        raise ProposalRejected("off_topic", "The storyline must be about them")
    return steps


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
            "role": "firmament_family",
            "status": status,
            "trace_id": str(uuid4()),
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "model": response.resolved_model if response else getattr(gateway, "model", "unknown"),
            "backend": response.backend if response else "unknown",
            "error_code": error_code,
            "simulated_at": at.isoformat(),
        },
    )
