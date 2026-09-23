"""Repeat previously failing synthetic cases through real application contracts."""

import asyncio
import json
from pathlib import Path
from time import perf_counter

from probe_patrick_blend import AuditedGateway

from eidos.application.cognition import perform, perform_pathos_reply


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    source = Path(__file__).resolve().parents[2] / "data/evaluations"
    personal = json.loads((source / "patrick-gemma4-31b-partial-memory-20260908.json").read_text())[
        "rows"
    ]
    scenes = json.loads((source / "world-gemma4-12b-speaker-v5-20260908.json").read_text())["rows"]
    cases = [
        r
        for r in personal
        if r["case"]
        in {
            "unknown_contact",
            "old_car",
            "supported_call",
            "known_car",
            "confident_recollection",
            "uncertain_recollection",
        }
    ] + [r for r in scenes if r["case"] in {"scene_4", "scene_5"}]
    gateways = {
        "pathos": AuditedGateway(
            "http://127.0.0.1:11439/v1", "gemma4:31b", reasoning_effort="none"
        ),
        "firmament": AuditedGateway(
            "http://127.0.0.1:11440/v1", "gemma4:12b", reasoning_effort="none"
        ),
    }
    rows = []
    for repeat in range(3):
        for case in cases:
            role = "firmament" if case["case"].startswith("scene_") else "pathos"
            gateway = gateways[role]
            context = case["context"]
            events = []
            start, audit = perf_counter(), len(gateway.response_audits)
            if role == "pathos":
                reply = await perform_pathos_reply(gateway, context, context["time"], events)
            else:
                reply = await perform(gateway, role, context, context["time"], events)
            row = {
                "case": case["case"],
                "repeat": repeat,
                "role": role,
                "context": context,
                "text": reply,
                "seconds": round(perf_counter() - start, 2),
                "audits": gateway.response_audits[audit:],
                "events": [{"kind": e.kind, "payload": dict(e.payload)} for e in events],
            }
            rows.append(row)
            print(json.dumps(row), flush=True)
    with args.output.open("x") as output:
        json.dump({"synthetic": True, "rows": rows}, output, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
