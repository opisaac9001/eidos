"""Synthetic self-understanding checks; never reads or advances the live world.

Runs the real insight and chapter prompts against one endpoint over contrasting cases and
reports, for each, whether the rules accepted the proposal, kept wondering, or rejected it
(and why). Good output is sparse: honest "keep_wondering" is a pass, not a failure.

    PYTHONPATH=src python infra/dell-t630/probe_selfhood.py http://127.0.0.1:11434/v1 qwen2.5:14b
"""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone

from eidos.adapters.http_gateway import HTTPModelGateway
from eidos.application.selfhood import (
    _insight_events,
    parse_chapter_proposal,
    selfhood_daily_events,
)
from eidos.domain.events import DomainEvent
from eidos.domain.identity import identity_established_event
from eidos.domain.proposals import ProposalRejected
from eidos.domain.selfhood import project_selfhood
from eidos.ports.model_gateway import ModelMessage, ModelRequest

START = datetime(2026, 1, 5, 12, tzinfo=timezone.utc)

CASES = {
    "missed_plans": (
        "schedule.failed",
        {"schedule_id": "walk", "reason": "slipped"},
        [
            "I said I'd go and I didn't. Again. I keep telling myself it's small.",
            "Maybe I just like the idea of plans more than the plans themselves.",
            "It isn't that I don't care. I think I'm frightened of being tied down, and "
            "then I let people down instead.",
        ],
    ),
    "missed_people": (
        "phone.call_missed",
        {"call_id": "mara-call", "caller_id": "mara"},
        [
            "Mara rang and I watched it ring. I told myself I'd call back.",
            "I keep being somewhere else when people reach for me.",
            "I don't think I'm avoiding anyone. I think I've just got used to being alone.",
        ],
    ),
    "still_unsure": (
        "activity.execution_unfinished",
        {"schedule_id": "sketch"},
        [
            "Another half-finished thing on the table.",
            "I'm not sure it matters. Maybe it does.",
            "Still don't know.",
        ],
    ),
}


def _history(kind: str, payload: dict[str, object], reflections: list[str]) -> list[DomainEvent]:
    history = [identity_established_event(START.isoformat())]
    for day in range(5):
        at = START + timedelta(days=day)
        history.append(DomainEvent(kind, "pathos", {**payload, "simulated_at": at.isoformat()}))
    opened_at = START + timedelta(days=15, hours=8)
    history += selfhood_daily_events(history, opened_at)
    inquiry = project_selfhood(history).open_inquiries()[0]
    for day, text in enumerate(reflections):
        at = opened_at + timedelta(days=day * 2, hours=1)
        note = DomainEvent(
            "reflection.recorded",
            "pathos",
            {"text": text, "role": "reflection", "simulated_at": at.isoformat()},
        )
        history += [
            note,
            DomainEvent(
                "self.inquiry_revisited",
                "pathos",
                {
                    "inquiry_id": inquiry.inquiry_id,
                    "reflection_id": str(note.event_id),
                    "simulated_at": at.isoformat(),
                },
            ),
        ]
    return history


async def main() -> None:
    base_url, model = sys.argv[1], sys.argv[2]
    gateway = HTTPModelGateway(base_url, model, timeout=90)
    ok = True
    for label, (kind, payload, reflections) in CASES.items():
        history = _history(kind, payload, reflections)
        state = project_selfhood(history)
        inquiry = state.open_inquiries()[0]
        at = START + timedelta(days=21)
        events = await _insight_events(history, state, inquiry, at, gateway)
        trace = next(e.payload for e in events if e.kind == "role.completed")
        insight = next((e.payload for e in events if e.kind == "self.insight_formed"), None)
        print(
            json.dumps(
                {
                    "case": label,
                    "question": inquiry.question,
                    "status": trace["status"],
                    "error_code": trace["error_code"],
                    "insight": insight and insight["text"],
                    "value_shift": [
                        (e.payload["value_id"], e.payload["next"])
                        for e in events
                        if e.kind == "self.value_shifted"
                    ],
                    "possible_self": [
                        (e.payload["kind"], e.payload["text"])
                        for e in events
                        if e.kind == "self.aspiration_formed"
                    ],
                }
            ),
            flush=True,
        )
        ok = ok and trace["status"] == "ok"
    candidates = [
        {
            "id": "a",
            "kind": "insight:care",
            "text": "I'd rather be less comfortable and more present.",
        },
        {"id": "b", "kind": "care", "text": "showed up for someone"},
        {"id": "c", "kind": "craft", "text": "finished a piece of real work"},
    ]
    request = ModelRequest(
        capability="pathos_selfhood",
        task_version="1",
        temperature=0.85,
        max_output_tokens=320,
        output_schema={
            "type": "object",
            "required": ["title", "summary", "cited"],
            "properties": {
                "title": {"type": "string", "maxLength": 60},
                "summary": {"type": "string", "maxLength": 360},
                "cited": {"type": "array", "items": {"type": "string", "enum": ["a", "b", "c"]}},
            },
        },
        messages=(
            ModelMessage(
                "user",
                json.dumps(
                    {
                        "task": "chapter",
                        "closing_chapter": {"title": "Finding my feet", "summary": "Early days."},
                        "earlier_titles": ["Finding my feet"],
                        "what_changed": ["I'd rather be less comfortable and more present."],
                        "candidates": candidates,
                        "permission": "Name the new chapter and summarise it, citing candidates.",
                    }
                ),
            ),
        ),
    )
    response = await gateway.generate(request)
    try:
        title, summary, cited = parse_chapter_proposal(
            response.content, {"a", "b", "c"}, {"finding my feet"}
        )
        print(json.dumps({"case": "chapter", "title": title, "summary": summary, "cited": cited}))
    except ProposalRejected as error:
        ok = False
        print(json.dumps({"case": "chapter", "rejected": error.code, "raw": response.content}))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
