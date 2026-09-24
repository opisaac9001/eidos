"""Natural life invariants, without requiring a scripted emotional itinerary."""

from datetime import datetime

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.domain.development import project_development


def test_nine_natural_days_preserve_replay_and_distinct_habit_evidence(tmp_path):
    path = tmp_path / "natural.sqlite3"
    life = Life(SQLiteEventStore(path), StandInGateway())
    assert life.authored_scenario is False
    for day in range(9):
        life.advance(24)
        if day == 3:
            before = life.snapshot()
            life = Life(SQLiteEventStore(path), StandInGateway())
            assert life.snapshot() == before
    history = life.history()
    snapshot = life.snapshot()
    assert Life(SQLiteEventStore(path), StandInGateway()).snapshot() == snapshot
    assert len({e.event_id for e in history}) == len(history)
    assert all(0 <= value <= 1 for value in snapshot["pathos"]["needs"].values())
    assert -1 <= snapshot["pathos"]["valence"] <= 1
    assert 0 <= snapshot["pathos"]["arousal"] <= 1
    # Projection validates provenance/lifecycle even when no habit forms. There is
    # deliberately no requirement to become happy, ill, or form a habit on cue.
    project_development(history)
    by_id = {str(e.event_id): e for e in history}
    for event in history:
        if event.kind not in {
            "habit.formed",
            "habit.reinforced",
            "habit.reactivated",
            "habit.weakened",
        }:
            continue
        count = event.payload.get("source_count")
        if count is None:  # Historical simple habit format has separate coverage.
            continue
        sources = [by_id[event.payload[f"source_event_{i}"]] for i in range(1, count + 1)]
        dates = [datetime.fromisoformat(e.payload["simulated_at"]).date() for e in sources]
        assert len(set(dates)) == len(dates)
    # Every activity he chose (not a work shift) is felt exactly once.
    chosen = {
        str(e.event_id)
        for e in history
        if e.kind == "agency.activity_realized"
        and not str(e.payload.get("schedule_id", "")).startswith("work-rota-")
    }
    felt = [e.payload["source_event_id"] for e in history if e.kind == "experience.felt"]
    assert len(felt) == len(set(felt))
    assert set(felt) == chosen
