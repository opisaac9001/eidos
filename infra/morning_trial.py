"""Isolated agency/execution comparison; no live history, deployment or clock changes.

Example: PYTHONPATH=src .venv/bin/python infra/morning_trial.py --output NEW_DIR
--base-url http://127.0.0.1:11439/v1 --model qwen2.5:14b
"""

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from uuid import UUID

from eidos.adapters.http_gateway import HTTPModelGateway
from eidos.application.agency import autonomous_activity_events
from eidos.application.lived_activity_window import lived_activity_window
from eidos.domain.actions import ActionKind
from eidos.domain.agency import AgencyCandidate, resolve_agency_candidate
from eidos.domain.events import DomainEvent
from eidos.domain.household import project_household
from eidos.domain.planning import project_planning
from eidos.domain.travel import route_duration
from eidos.domain.world_catalog import project_world_catalog

WORK_START = datetime(2026, 1, 8, 9, tzinfo=timezone.utc)


def morning_fixture(free_minutes, *, energy=0.7, connection=0.6):
    catalog = project_world_catalog([])
    travel = route_duration("home", "workshop", catalog.route_minutes)
    now = WORK_START - travel - timedelta(minutes=free_minutes)
    history = [
        DomainEvent("sleep.ended", "pathos", {"simulated_at": now.isoformat()}),
        DomainEvent(
            "affect.changed",
            "pathos",
            {
                "energy": energy,
                "valence": 0.0,
                "arousal": 0.35,
                "simulated_at": now.isoformat(),
            },
        ),
        DomainEvent(
            "household.established",
            "pathos",
            {
                "dishes": 0.8,
                "laundry": 0.2,
                "tidying": 0.1,
                "paperwork": 0.1,
                "simulated_at": now.isoformat(),
            },
        ),
    ]
    resolution = resolve_agency_candidate(
        AgencyCandidate(
            "workshop_shift",
            "Work at the workshop",
            "Keep my accepted work appointment",
            ActionKind.WORK,
            "workshop",
            None,
            None,
            (WORK_START - now).total_seconds() / 3600,
            1.0,
            0.9,
        ),
        proposal_id="fixture-work",
        state=project_planning(history),
        catalog=catalog,
        known_companion_ids=set(),
        actual_revision=len(history),
        simulated_at=now,
    )
    assert resolution.accepted, resolution.code
    history.extend(resolution.events)
    history.append(
        DomainEvent(
            "thought.recorded",
            "pathos",
            {
                "text": "There's a pile by the sink. What do I actually feel like doing before work?",
                "simulated_at": now.isoformat(),
            },
            event_id=UUID("00000000-0000-0000-0000-000000000007"),
        )
    )
    needs = {"energy": energy, "rest": energy, "connection": connection, "hunger": 0.3}
    return now, history, needs


class Recorder:
    def __init__(self, gateway):
        self.gateway = gateway
        self.calls = []

    async def generate(self, request):
        start = perf_counter()
        response = await self.gateway.generate(request)
        self.calls.append(
            {
                "context": json.loads(request.messages[-1].content),
                "reply": response.content,
                "model": response.resolved_model,
                "finish_reason": response.finish_reason,
                "seconds": perf_counter() - start,
            }
        )
        return response


async def run_case(gateway, free_minutes, *, energy=0.7, connection=0.6):
    now, history, needs = morning_fixture(free_minutes, energy=energy, connection=connection)
    recorder = Recorder(gateway)
    chosen = await autonomous_activity_events(
        history,
        now,
        len(history),
        recorder,
        planning=project_planning(history),
        catalog=project_world_catalog(history),
        needs=needs,
        emotion={"label": "quiet", "valence": 0.0, "arousal": 0.35},
        values={},
        preferences=[],
        traits={},
        memories=[],
        current_location_id="home",
    )
    history.extend(chosen)
    end = WORK_START + timedelta(minutes=30)
    history.extend(
        lived_activity_window(
            history,
            project_planning(history),
            project_world_catalog(history),
            now,
            end,
            repair_mastery=0.5,
        )
    )
    return {
        "free_minutes": free_minutes,
        "needs": needs,
        "calls": recorder.calls,
        "decisions": [
            {"kind": e.kind, "payload": dict(e.payload)}
            for e in chosen
            if e.kind in {"schedule.created", "agency.activity_rejected", "role.failed"}
        ],
        "dish_load_after": project_household(history).loads["dishes"],
        "execution": [
            {"kind": e.kind, "payload": dict(e.payload)}
            for e in history
            if e.kind
            in {
                "activity.stage_completed",
                "household.task_completed",
                "schedule.completed",
                "pathos.travel_started",
                "pathos.travel_arrived",
            }
        ],
    }


async def main(args):
    args.output.mkdir(parents=True, exist_ok=False)
    gateway = HTTPModelGateway(args.base_url, args.model, timeout=45, reasoning_effort="none")
    results = []
    for repeat in range(args.repeats):
        for free, energy, connection in (
            (15, 0.7, 0.6),
            (40, 0.7, 0.6),
            (90, 0.7, 0.6),
            (40, 0.2, 0.2),
        ):
            row = await run_case(gateway, free, energy=energy, connection=connection)
            row["repeat"] = repeat + 1
            results.append(row)
            (args.output / "results.json").write_text(json.dumps(results, indent=2, default=str))
            print(
                json.dumps(
                    {k: row[k] for k in ("free_minutes", "needs", "dish_load_after", "decisions")}
                ),
                flush=True,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=3)
    asyncio.run(main(parser.parse_args()))
