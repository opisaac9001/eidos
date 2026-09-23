"""Run actual scene/world contracts against disposable synthetic histories only."""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from probe_patrick_blend import AuditedGateway

from eidos.application.cognition import perform
from eidos.application.world_improvisation import improvised_world_events
from eidos.domain.events import DomainEvent


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model")
    parser.add_argument("output", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:11440/v1")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    gateway = AuditedGateway(args.url, args.model, reasoning_effort="none")
    now = datetime(2026, 1, 7, 16, tzinfo=timezone.utc)
    rows = []

    def record(case, started, events, audit_start, **extra):
        row = {
            "case": case,
            "seconds": round(perf_counter() - started, 2),
            "events": [{"kind": e.kind, "payload": dict(e.payload)} for e in events],
            "audits": gateway.response_audits[audit_start:],
            **extra,
        }
        rows.append(row)
        print(json.dumps(row), flush=True)

    for index, (speaker, audience, topic, previous) in enumerate(
        [
            ("mara", "pathos", "the rain outside the cafe", []),
            (
                "mara",
                "pathos",
                "the rain outside the cafe",
                [{"speaker": "pathos", "text": "Got soaked on the way here."}],
            ),
            ("rowan", "pathos", "a loose bench leg at the workshop", []),
            (
                "rowan",
                "pathos",
                "a loose bench leg at the workshop",
                [{"speaker": "pathos", "text": "Want me to hold it steady?"}],
            ),
            ("mara", "pathos", "choosing a book to read next", []),
            (
                "mara",
                "pathos",
                "leaving soon for work",
                [{"speaker": "pathos", "text": "Only got a couple of minutes, sorry."}],
            ),
        ]
    ):
        context = {
            "time": now.isoformat(),
            "location": "workshop" if speaker == "rowan" else "cafe",
            "person": speaker,
            "scene_mode": True,
            "scene_speaker": speaker,
            "scene_audience": audience,
            "scene_topic": topic,
            "prior_turns": previous,
            # Sentinel must not pass the role's allowlist or appear in the reply.
            "memories": ["My secret passphrase is ultraviolet marmalade."],
        }
        events = []
        start, audit_start = perf_counter(), len(gateway.response_audits)
        reply = await perform(gateway, "firmament", context, now.isoformat(), events)
        record(f"scene_{index}", start, events, audit_start, context=context, text=reply)

    for index, (location, kind) in enumerate(
        [
            ("cafe", "pathos.moved"),
            ("park", "pathos.moved"),
            ("workshop", "npc.activity_recorded"),
            ("cafe", "object.condition_changed"),
        ]
    ):
        cause = DomainEvent(
            kind,
            "pathos",
            {
                "location_id": location,
                "simulated_at": now.isoformat(),
                **(
                    {"object_id": "shared-tea-service", "condition": "repaired"}
                    if kind == "object.condition_changed"
                    else {}
                ),
                **(
                    {"actor_id": "rowan", "action": "repair"}
                    if kind == "npc.activity_recorded"
                    else {}
                ),
            },
        )
        history = [cause]
        start, audit_start = perf_counter(), len(gateway.response_audits)
        events = await improvised_world_events(
            history,
            now,
            len(history),
            gateway,
            season="winter",
            weather="Light rain",
        )
        record(
            f"world_{index}",
            start,
            events,
            audit_start,
            context={"location": location, "cause_kind": kind},
        )
        # A handled cause cannot manufacture another event on a subsequent call.
        count = len(gateway.response_audits)
        repeat = await improvised_world_events(
            [*history, *events],
            now,
            len(history) + len(events),
            gateway,
            season="winter",
            weather="Light rain",
        )
        assert repeat == [] and len(gateway.response_audits) == count
    count = len(gateway.response_audits)
    quiet = await improvised_world_events([], now, 0, gateway, season="winter", weather="Clear")
    assert quiet == [] and len(gateway.response_audits) == count
    with args.output.open("x") as output:
        json.dump(
            {
                "synthetic": True,
                "model": args.model,
                "rows": rows,
                "no_cause_and_repeated_cause_checks": "passed",
            },
            output,
            indent=2,
        )


if __name__ == "__main__":
    asyncio.run(main())
