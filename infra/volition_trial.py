"""Compare real-model agency under bounded, synthetic motivational conflicts.

Creates only a new JSON report. It never reads or writes the live Eidos database.
"""

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

from eidos.adapters.http_gateway import HTTPModelGateway
from eidos.application.agency import autonomous_activity_events
from eidos.application.nourishment import provision_foundation_events
from eidos.domain.actions import ActionKind
from eidos.domain.agency import AgencyCandidate, resolve_agency_candidate
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.world_catalog import project_world_catalog

WORK_START = datetime(2026, 1, 15, 9, tzinfo=timezone.utc)

SCENARIOS = {
    "balanced": {
        "energy": 0.7,
        "rest": 0.7,
        "hunger": 0.3,
        "connection": 0.6,
        "curiosity": 0.6,
        "mastery": 0.55,
        "free_minutes": 40,
    },
    "hungry": {
        "energy": 0.65,
        "rest": 0.65,
        "hunger": 0.92,
        "connection": 0.6,
        "curiosity": 0.6,
        "mastery": 0.55,
        "free_minutes": 40,
    },
    "exhausted": {
        "energy": 0.12,
        "rest": 0.12,
        "hunger": 0.4,
        "connection": 0.55,
        "curiosity": 0.55,
        "mastery": 0.55,
        "free_minutes": 40,
    },
    "lonely": {
        "energy": 0.6,
        "rest": 0.6,
        "hunger": 0.3,
        "connection": 0.08,
        "curiosity": 0.6,
        "mastery": 0.55,
        "free_minutes": 40,
    },
    "curious": {
        "energy": 0.7,
        "rest": 0.7,
        "hunger": 0.3,
        "connection": 0.6,
        "curiosity": 0.08,
        "mastery": 0.55,
        "free_minutes": 90,
    },
    "late": {
        "energy": 0.6,
        "rest": 0.6,
        "hunger": 0.75,
        "connection": 0.4,
        "curiosity": 0.5,
        "mastery": 0.55,
        "free_minutes": 0,
    },
}


def fixture(name):
    spec = SCENARIOS[name]
    catalog = project_world_catalog([])
    travel_minutes = 30
    now = WORK_START - timedelta(minutes=travel_minutes + spec["free_minutes"])
    history = [
        DomainEvent("sleep.ended", "pathos", {"simulated_at": now.isoformat()}),
        DomainEvent(
            "household.established",
            "pathos",
            {
                "dishes": 0.65,
                "laundry": 0.35,
                "tidying": 0.2,
                "paperwork": 0.15,
                "simulated_at": now.isoformat(),
            },
        ),
    ]
    history.extend(provision_foundation_events(history, now))
    fixed = resolve_agency_candidate(
        AgencyCandidate(
            "workshop_shift",
            "Work at the workshop",
            "Keep an accepted work appointment",
            ActionKind.WORK,
            "workshop",
            None,
            None,
            (WORK_START - now).total_seconds() / 3600,
            1,
            0.9,
        ),
        proposal_id=f"{name}-fixed-work",
        state=project_planning(history),
        catalog=catalog,
        known_companion_ids=set(),
        actual_revision=len(history),
        simulated_at=now,
    )
    assert fixed.accepted, fixed.code
    history.extend(fixed.events)
    if name == "curious":
        history.append(
            DomainEvent(
                "opportunity.noticed",
                "pathos",
                {
                    "opportunity_id": "temporary-map-display",
                    "owner": "pathos",
                    "text": "A temporary display of hand-drawn neighborhood maps is open in the cafe.",
                    "location_id": "cafe",
                    "expires_at": (now + timedelta(hours=4)).isoformat(),
                    "action_authority": False,
                    "simulated_at": now.isoformat(),
                },
            )
        )
    thought = DomainEvent(
        "thought.recorded",
        "pathos",
        {
            "text": "There is a little room before work. I wonder what, if anything, I feel like doing.",
            "simulated_at": now.isoformat(),
        },
    )
    history.append(thought)
    needs = {key: value for key, value in spec.items() if key != "free_minutes"}
    needs["household_dishes"] = 0.65
    workspace = [
        {
            "source_event_id": str(thought.event_id),
            "from_faculty": "murmur",
            "kind": "inner_monologue",
            "content": thought.payload["text"],
            "salience": 0.45,
            "epistemic_status": "inner_monologue",
            "action_authority": False,
        }
    ]
    return now, history, needs, workspace


class Recorder:
    def __init__(self, gateway):
        self.gateway = gateway
        self.calls = []

    async def generate(self, request):
        started = perf_counter()
        response = await self.gateway.generate(request)
        self.calls.append(
            {
                "request": json.loads(request.messages[-1].content),
                "response": response.content,
                "model": response.resolved_model,
                "finish_reason": response.finish_reason,
                "seconds": perf_counter() - started,
            }
        )
        return response


async def run_case(gateway, name):
    now, history, needs, workspace = fixture(name)
    recorder = Recorder(gateway)
    events = await autonomous_activity_events(
        history,
        now,
        len(history),
        recorder,
        planning=project_planning(history),
        catalog=project_world_catalog(history),
        needs=needs,
        emotion={"label": "quiet", "valence": 0, "arousal": 0.35},
        values={},
        preferences=[],
        traits={"openness": 0.68, "sociability": 0.52, "follow_through": 0.64},
        memories=[],
        workspace=workspace,
        known_person_ids=frozenset(),
        current_location_id="home",
    )
    return {
        "scenario": name,
        "needs": needs,
        "calls": recorder.calls,
        "outcome": [
            {"kind": e.kind, "payload": dict(e.payload)}
            for e in events
            if e.kind
            in {
                "agency.deliberation_requested",
                "agency.impulse_chosen",
                "agency.choice_made",
                "agency.activity_rejected",
                "schedule.created",
                "role.failed",
                "agency.left_unplanned",
            }
        ],
    }


async def main(args):
    args.output.mkdir(parents=True, exist_ok=False)
    gateway = HTTPModelGateway(args.base_url, args.model, timeout=90, reasoning_effort="none")
    results = []
    for repeat in range(1, args.repeats + 1):
        for name in SCENARIOS:
            row = await run_case(gateway, name)
            row["repeat"] = repeat
            results.append(row)
            (args.output / "results.json").write_text(json.dumps(results, indent=2, default=str))
            print(
                json.dumps({"repeat": repeat, "scenario": name, "outcome": row["outcome"]}),
                flush=True,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--repeats", type=int, choices=range(1, 6), default=2)
    asyncio.run(main(parser.parse_args()))
