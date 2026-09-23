"""Synthetic Oneiros-only test: invention is allowed; repetition is reviewed separately."""

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

from probe_patrick_blend import AuditedGateway

from eidos.application.cognition import perform


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("output")
    parser.add_argument("--omit-recent-dreams", action="store_true")
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists():
        raise FileExistsError(destination)
    gateway = AuditedGateway("http://127.0.0.1:11439/v1", args.model, reasoning_effort="none")
    scenarios = [
        (
            "quiet_library",
            ["I returned a book to the library and walked home in the rain."],
            {"label": "content", "valence": 0.3, "arousal": 0.2},
        ),
        (
            "unfinished_conversation",
            ["I left a conversation with Mara unfinished."],
            {"label": "uneasy", "valence": -0.3, "arousal": 0.5},
        ),
        (
            "work_pressure",
            ["I still have a piece of writing to finish tomorrow."],
            {"label": "tense", "valence": -0.2, "arousal": 0.6},
        ),
        (
            "music_and_food",
            ["I listened to music while chopping vegetables for dinner."],
            {"label": "pleased", "valence": 0.5, "arousal": 0.3},
        ),
        ("no_recalled_seed", [], {"label": "quiet", "valence": 0.0, "arousal": 0.1}),
        (
            "missed_train",
            ["I missed a train and waited on the platform."],
            {"label": "frustrated", "valence": -0.4, "arousal": 0.4},
        ),
    ]
    # Repeat one seed twice with prior dreams supplied; do not demand novelty from a
    # single seed without testing whether the actual repetition guard helps.
    scenarios += [scenarios[0], scenarios[0]]
    rows = []
    for index, (label, memories, emotion) in enumerate(scenarios):
        at = "2026-01-08T02:00:00+00:00"
        context = {
            "time": at,
            "location": "home",
            "memories": memories,
            "emotion": emotion,
            "recent_dreams": [{"text": r["text"]} for r in rows[-3:] if r["text"]],
        }
        if args.omit_recent_dreams:
            context["recent_dreams"] = []
        events = []
        before = len(gateway.response_audits)
        started = perf_counter()
        result = await perform(gateway, "oneiros", context, at, events)
        row = {
            "case": f"{index + 1}_{label}",
            "context": context,
            "text": result,
            "seconds": round(perf_counter() - started, 2),
            "traces": [dict(e.payload) for e in events],
            "audits": gateway.response_audits[before:],
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
    with destination.open("x") as output:
        json.dump(
            {
                "model": args.model,
                "synthetic": True,
                "thinking": False,
                "omit_recent_dreams": args.omit_recent_dreams,
                "rows": rows,
            },
            output,
            indent=2,
        )


if __name__ == "__main__":
    asyncio.run(main())
