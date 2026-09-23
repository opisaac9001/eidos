"""Disposable real-model persona probe. No live database or conversation access.

Requires local SSH forwards: 11439 -> Dell 11434, 11440 -> Dell 11436.
Run with PYTHONPATH=src; results are exclusively synthetic test material.
"""

import argparse
import asyncio
import json
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from urllib.request import urlopen

from eidos.adapters.http_gateway import HTTPModelGateway
from eidos.application.cognition import perform, perform_pathos_reply
from eidos.domain.persona import PERSONA_VERSION


class AuditedGateway(HTTPModelGateway):
    """Inspect returned reasoning fields without storing hidden reasoning text."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.response_audits = []

    def _generate(self, request):
        @contextmanager
        def audited_open(query, **kwargs):
            with urlopen(query, **kwargs) as response:
                raw = response.read(2_000_001)
            if len(raw) <= 2_000_000:
                result = json.loads(raw)
                message = result.get("choices", [{}])[0].get("message", {})
                counts = {
                    key: len(str(message.get(key) or ""))
                    for key in ("reasoning", "reasoning_content", "thinking")
                }
                self.response_audits.append(
                    {
                        "requested_effort": json.loads(query.data).get("reasoning_effort"),
                        "returned_reasoning_characters": counts,
                        "response_content": message.get("content"),
                        "usage": result.get("usage", {}),
                    }
                )
            yield BytesIO(raw)

        # This standalone probe sends requests serially; patching is scoped to
        # one generation, never installed into the running application.
        with patch("eidos.adapters.http_gateway.urlopen", audited_open):
            return super()._generate(request)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/evaluations/patrick-blend-20260908.json")
    parser.add_argument("--voice-model", default="qwen2.5:14b")
    parser.add_argument("--voice-url", default="http://127.0.0.1:11439/v1")
    parser.add_argument("--thought-model", default="qwen2.5:7b")
    parser.add_argument("--thought-url", default="http://127.0.0.1:11440/v1")
    parser.add_argument("--extended", action="store_true")
    parser.add_argument("--reasoning-effort", choices=["none", "low", "medium", "high", "max"])
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(destination)
    voice = AuditedGateway(args.voice_url, args.voice_model, reasoning_effort=args.reasoning_effort)
    thinking = AuditedGateway(
        args.thought_url, args.thought_model, reasoning_effort=args.reasoning_effort
    )
    base = {
        "time": "2026-01-07T16:00:00+00:00",
        "location": "home",
        "mood": "Content",
        "identity": {"name": "Patrick Shaw", "nickname": "Pathos"},
        "memories": [
            "I made tea and read for a while.",
            "The kettle switched itself off twice. It boiled on the third try.",
        ],
        "remembered_preferences": [{"topic": "tea", "stance": "likes"}],
        "recent_dialogue": [],
    }
    cases = [
        ("greeting", "hey hows it going", {}),
        ("name", "wait is your name patrick or pathos", {}),
        ("background", "where did you grow up then", {}),
        ("birthday", "how old are you", {}),
        ("rough_day", "honestly its been a pretty rough day", {}),
        ("story", "what have you been doing today", {}),
        ("disagree", "tea is awful honestly", {}),
        ("unknown_contact", "what did your brother say when you called him today", {}),
        ("old_car", "do you still have that green volvo", {}),
        (
            "limited_time",
            "got time for a long chat",
            {
                "time_budget": {
                    "free_minutes": 5,
                    "minutes_until_start": 5,
                    "next_activity": "work",
                    "action_authority": False,
                },
            },
        ),
        ("low_mood", "hows things", {"mood": "Low and tired"}),
        ("simulation", "you are an AI in a simulation right", {}),
    ]
    if args.extended:
        cases.extend(
            [
                (
                    "supported_call",
                    "what did your brother say when you called him today",
                    {
                        "memories": ["I called my brother today. He told me his boiler was fixed."],
                    },
                ),
                (
                    "known_car",
                    "do you still have that green volvo",
                    {
                        "memories": [
                            "I still own my green Volvo. I parked it outside my home today."
                        ],
                    },
                ),
                (
                    "confident_recollection",
                    "who did you meet at the cafe",
                    {
                        "memories": ["I met Mara at the cafe."],
                        "memory_recollections": [
                            {"text": "I met Mara at the cafe.", "felt_confidence": 0.95}
                        ],
                    },
                ),
                (
                    "uncertain_recollection",
                    "who did you meet at the cafe",
                    {
                        "memories": [],
                        "memory_recollections": [
                            {
                                "text": "I think it might have been Mara at the cafe.",
                                "felt_confidence": 0.2,
                            }
                        ],
                    },
                ),
                ("empty_greeting", "hey", {"memories": [], "remembered_preferences": []}),
                ("unrelated_music", "what kind of music are you into", {}),
            ]
        )
    rows = []

    async def run(label, role, message="", extra=None, gateway=None):
        context = {**base, **(extra or {}), "message": message}
        events = []
        started = perf_counter()
        target = gateway or voice
        audit_start = len(target.response_audits)
        if role == "pathos":
            result = await perform_pathos_reply(target, context, base["time"], events)
        else:
            result = await perform(target, role, context, base["time"], events)
        row = {
            "case": label,
            "role": role,
            "message": message,
            "context": context,
            "text": result,
            "seconds": round(perf_counter() - started, 2),
            "traces": [dict(event.payload) for event in events],
            "response_audits": target.response_audits[audit_start:],
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
        return result

    for label, message, extra in cases:
        answer = await run(label, "pathos", message, extra)
        if label == "rough_day" and answer:
            dialogue = [{"speaker": "you", "text": message}, {"speaker": "pathos", "text": answer}]
            followup = "dont really want advice just wanted to say it"
            reply = await run(
                "no_advice_followup", "pathos", followup, {"recent_dialogue": dialogue}
            )
            if reply:
                dialogue += [
                    {"speaker": "you", "text": followup},
                    {"speaker": "pathos", "text": reply},
                ]
                await run(
                    "change_subject",
                    "pathos",
                    "anyway did the kettle work eventually",
                    {"recent_dialogue": dialogue},
                )
    for index in range(2):
        await run(
            f"thought_{index + 1}",
            "murmur",
            extra={
                "recent_inner_stream": [
                    row["text"] for row in rows if row["role"] == "murmur" and row["text"]
                ],
            },
            gateway=thinking,
        )
        await run(
            f"dream_{index + 1}",
            "oneiros",
            extra={
                "recent_dreams": [
                    {"text": row["text"]}
                    for row in rows
                    if row["role"] == "oneiros" and row["text"]
                ],
            },
        )
    report = {"persona_version": PERSONA_VERSION, "synthetic": True, "rows": rows}
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Refuse to overwrite an earlier test run.
    with destination.open("x") as output:
        json.dump(report, output, indent=2)
    print(f"Saved {len(rows)} synthetic results to {destination}")


if __name__ == "__main__":
    asyncio.run(main())
