"""Validate a staged release against a disposable copy, never the live database."""

import json
import sys
from pathlib import Path

from eidos.adapters.sqlite_backup import create_backup, verify_backup
from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life


def run(source: Path, destination: Path) -> None:
    if source.resolve() == Path("/var/lib/eidos/observatory.sqlite3"):
        raise ValueError("Use a verified backup as input, not the live database")
    if destination.resolve() == Path("/var/lib/eidos/observatory.sqlite3"):
        raise ValueError("Never use the live database as the replay destination")
    report = create_backup(source, destination)
    simulation = Life(SQLiteEventStore(destination), StandInGateway())
    before = simulation.snapshot()
    original_events = simulation.history()
    assert len(original_events) == report.event_count
    assert before["config"]["running"] is False, "Expected a paused source world"
    simulation.advance(2)
    after = simulation.snapshot()
    assert simulation.history()[: len(original_events)] == original_events
    restarted = Life(SQLiteEventStore(destination), StandInGateway()).snapshot()
    assert restarted["time"] == after["time"]
    assert restarted["revision"] == after["revision"]
    assert restarted["activity_execution"] == after["activity_execution"]
    checked = verify_backup(destination)
    print(
        json.dumps(
            {
                "integrity": checked.integrity,
                "source_events": report.event_count,
                "initial_time": before["time"],
                "copy_time_after_two_hours": after["time"],
                "copy_events": after["revision"],
                "history_prefix_preserved": True,
                "restart_replay_passed": True,
                "models": "stand-in only",
                "live_database_touched": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]))
