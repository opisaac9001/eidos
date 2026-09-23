"""Disposable lived-day preview and bounded real-model trial; never reads live data.

The caller supplies a NEW output directory. Model mode uses existing local SSH
forwards: 11439 Pathos, 11441 world, 11440 small cognition. No model promotion.
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from eidos.adapters.http_gateway import HTTPModelGateway
from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.activity_execution import execution_context
from eidos.application.cognition import perform, perform_pathos_reply
from eidos.application.household import household_foundation_events
from eidos.application.life import Life
from eidos.application.personal_journeys import journey_context
from eidos.application.relationship_experience import personal_relationship_context
from eidos.domain.actions import ActionKind
from eidos.domain.agency import AgencyCandidate, resolve_agency_candidate
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.world_catalog import project_world_catalog

NOW = datetime(2026, 1, 8, 10, 10, tzinfo=timezone.utc)


def seed(path: Path) -> Life:
    store = SQLiteEventStore(path)
    history = [
        DomainEvent(
            "simulation.preview_established",
            "pathos",
            {"simulated_at": NOW.isoformat(), "synthetic_only": True},
        ),
        DomainEvent("time.advanced", "pathos", {"simulated_at": NOW}),
        DomainEvent("sleep.ended", "pathos", {"simulated_at": NOW.isoformat()}),
        *household_foundation_events([], NOW),
    ]
    # Two explicitly chosen synthetic activities. The planner is not told to
    # manufacture these in the real world; they are controlled test fixtures.
    for key, candidate in (
        (
            # This replay-stable sample finishes just before its estimate. The
            # companion fixture below runs slightly long, so the preview covers
            # both sides of Patrick's imperfect duration estimates.
            "trial-dishes-37",
            AgencyCandidate(
                "household_dishes",
                "Wash the dishes",
                "The kitchen could use some attention",
                ActionKind.WORK,
                "home",
                None,
                None,
                0,
                0.5,
                0.8,
            ),
        ),
        (
            "trial-workshop",
            AgencyCandidate(
                "letter_writing",
                "Write a letter at the workshop",
                "I want a change of scene",
                ActionKind.WORK,
                "workshop",
                None,
                None,
                1,
                0.5,
                0.8,
            ),
        ),
    ):
        result = resolve_agency_candidate(
            candidate,
            proposal_id=key,
            state=project_planning(history),
            catalog=project_world_catalog(history),
            known_companion_ids=set(),
            actual_revision=len(history),
            simulated_at=NOW,
        )
        assert result.accepted, result.code
        history.extend(result.events)
    store.append("pathos", history, 0)
    return Life(store, StandInGateway())


class TrialGateway:
    def __init__(self, voice_model="qwen2.5:14b", world_model="qwen2.5:14b"):
        self.personal = HTTPModelGateway(
            "http://127.0.0.1:11439/v1", voice_model, timeout=90, reasoning_effort="none"
        )
        self.world = HTTPModelGateway(
            "http://127.0.0.1:11441/v1", world_model, timeout=90, reasoning_effort="none"
        )
        self.small = HTTPModelGateway(
            "http://127.0.0.1:11440/v1", "qwen2.5:7b", timeout=90, reasoning_effort="none"
        )
        self.calls = []

    async def generate(self, request):
        gateway = (
            self.personal
            if request.capability in {"pathos", "pathos_agency", "logos"}
            else self.world
            if request.capability in {"firmament", "moira", "moira_event", "moira_expansion"}
            else self.small
        )
        start = perf_counter()
        try:
            response = await gateway.generate(request)
        except Exception as error:
            self.calls.append(
                {
                    "role": request.capability,
                    "error": type(error).__name__,
                    "seconds": perf_counter() - start,
                }
            )
            raise
        self.calls.append(
            {
                "role": request.capability,
                "model": response.resolved_model,
                "task_version": request.task_version,
                "seconds": round(perf_counter() - start, 3),
                "text": response.content,
                "finish_reason": response.finish_reason,
                "thinking_requested": "none",
            }
        )
        return response


def context(life: Life, message: str):
    history = life.history()
    state = life.project(history)
    return {
        "time": state.simulated_at.isoformat(),
        "message": message,
        "identity": {"name": "Patrick Shaw", "nickname": "Pathos"},
        "location": project_world_catalog(history).location_name(state.location_id),
        "journey": journey_context(history, state.simulated_at, project_world_catalog(history)),
        "ongoing_activities": execution_context(
            history, project_planning(history), state.simulated_at
        ),
        "memories": [],
        "recent_dialogue": [],
    }


async def trial(directory: Path, voice_model: str, world_model: str, hours: int, repeats: int):
    gateway = TrialGateway(voice_model, world_model)
    life = seed(directory / "world.sqlite3")
    await life._advance(5 / 60)
    working = context(life, "Are the dishes done yet?")
    await life._advance(25 / 60)
    done = context(life, "Did you finish the dishes?")
    await life._advance(29 / 60)
    travelling = context(life, "Are you at the workshop yet?")
    assert travelling["journey"] is not None
    cases = [
        ("working", "pathos", working),
        ("finished", "pathos", done),
        ("travelling", "pathos", travelling),
    ]
    interrupted = dict(
        working,
        message="Did you finish everything before you stopped?",
        ongoing_activities=[
            dict(working["ongoing_activities"][0], interruption="conversation", unfinished=True)
        ],
    )
    cases.append(("interrupted", "pathos", interrupted))
    for kind in ("commitment.missed", "commitment.fulfilled", "apology.offered"):
        history = [
            DomainEvent(
                "commitment.created",
                "pathos",
                {
                    "commitment_id": "book",
                    "debtor_id": "pathos",
                    "creditor_id": "mara",
                    "title": "Return my book",
                    "simulated_at": NOW.isoformat(),
                },
            ),
            DomainEvent(
                "commitment.missed" if kind == "apology.offered" else kind,
                "pathos",
                {"commitment_id": "book", "simulated_at": NOW.isoformat()},
            ),
        ]
        if kind == "apology.offered":
            history.append(
                DomainEvent(
                    kind,
                    "pathos",
                    {"actor_id": "pathos", "target_id": "mara", "simulated_at": NOW.isoformat()},
                )
            )
        cases.append(
            (
                kind,
                "firmament",
                {
                    "time": NOW.isoformat(),
                    "location": "cafe",
                    "person": "Mara",
                    "scene_mode": True,
                    "scene_speaker": "mara",
                    "scene_audience": "pathos",
                    "scene_topic": "borrowing another book",
                    "prior_turns": [
                        {"speaker": "pathos", "text": "Could I borrow another book sometime?"}
                    ],
                    "personal_relationship_context": personal_relationship_context(
                        history, "mara", "pathos", NOW
                    ),
                },
            )
        )
    rows = []
    for repeat in range(repeats):
        for name, role, supplied in cases:
            events = []
            reply = (
                await perform_pathos_reply(gateway, supplied, supplied["time"], events)
                if role == "pathos"
                else await perform(gateway, role, supplied, supplied["time"], events)
            )
            row = {
                "case": name,
                "repeat": repeat,
                "context": supplied,
                "text": reply,
                "events": [{"kind": e.kind, "payload": dict(e.payload)} for e in events],
            }
            rows.append(row)
            print(json.dumps({"case": name, "repeat": repeat, "text": reply}), flush=True)
    # Exercise independent workers together without monkeypatching HTTP globals.
    start = perf_counter()
    await asyncio.gather(
        perform_pathos_reply(gateway, working, working["time"], []),
        perform(gateway, "firmament", cases[-1][2], NOW.isoformat(), []),
        perform(gateway, "murmur", travelling, travelling["time"], []),
    )
    concurrent_seconds = perf_counter() - start
    # The very same synthetic saved life now runs through the actual application
    # with real performers, then is reopened to verify persistence/replay.
    live = Life(SQLiteEventStore(directory / "world.sqlite3"), gateway, mode="local-model")
    before = len(live.history())
    for _ in range(hours * 2):
        await live._advance(0.5)
        print(
            json.dumps({"soak_time": live.snapshot()["time"], "revision": len(live.history())}),
            flush=True,
        )
    snapshot = live.snapshot()
    restored = Life(SQLiteEventStore(directory / "world.sqlite3"), gateway, mode="local-model")
    assert restored.snapshot() == snapshot
    events = live.history()[before:]
    report = {
        "synthetic_only": True,
        "rows": rows,
        "calls": gateway.calls,
        "concurrent_seconds": concurrent_seconds,
        "soak": {
            "hours": hours,
            "events": len(events),
            "role_failures": [dict(e.payload) for e in events if e.kind == "role.failed"],
            "exact_restart": True,
            "final_time": snapshot["time"],
        },
    }
    (directory / "results.json").write_text(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--models", action="store_true")
    parser.add_argument("--voice-model", default="qwen2.5:14b")
    parser.add_argument("--world-model", default="qwen2.5:14b")
    parser.add_argument("--hours", type=int, choices=range(1, 25), default=2)
    parser.add_argument("--repeats", type=int, choices=range(4), default=3)
    args = parser.parse_args()
    args.directory.mkdir(exist_ok=False)
    if args.models:
        asyncio.run(
            trial(args.directory, args.voice_model, args.world_model, args.hours, args.repeats)
        )
    else:
        life = seed(args.directory / "world.sqlite3")
        life.advance(5 / 60)
        print(args.directory / "world.sqlite3")


if __name__ == "__main__":
    main()
