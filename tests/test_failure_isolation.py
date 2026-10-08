"""One part of his hour going wrong is skipped and recorded; his world goes on."""

from datetime import datetime

import pytest

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.domain.events import DomainEvent


def _breaking(life: Life) -> None:
    def broken(tick) -> None:
        # Half done, then a bug: what it added must not be kept.
        tick.pending.append(
            DomainEvent("memory.recorded", "pathos", {"text": "half-made", "simulated_at": tick.at})
        )
        raise KeyError("lean")

    life._phase_town_issues = broken  # type: ignore[method-assign]


def test_a_failing_part_is_rolled_back_and_the_hour_goes_on(tmp_path) -> None:
    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(2)
    before = datetime.fromisoformat(life.snapshot()["time"])
    life.isolate_failures = True
    _breaking(life)
    life.advance(3)
    history = life.history()
    assert datetime.fromisoformat(life.snapshot()["time"]) > before
    failed = [e for e in history if e.kind == "life.phase_failed"]
    assert len(failed) == 3 and failed[0].payload["phase"] == "broken"
    assert "KeyError" in failed[0].payload["error"]
    assert not any(e.payload.get("text") == "half-made" for e in history)
    assert life.phase_failures[-1]["phase"] == "broken"
    # Other parts of the hour still happened.
    assert any(e.kind == "time.advanced" for e in history[-200:])


def test_tests_still_see_failures(tmp_path) -> None:
    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    _breaking(life)
    with pytest.raises(KeyError):
        life.advance(2)
