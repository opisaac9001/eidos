"""Shifts are made of actual jobs: things brought in, setbacks, finishing, collection."""

from datetime import datetime, timedelta, timezone

from eidos.application.feelings import feeling_events
from eidos.application.repair_jobs import (
    COLLECTED,
    FINISHED,
    SETBACK,
    TAKEN,
    WORKED,
    bench_view,
    jobs,
    repair_job_events,
)
from eidos.domain.events import DomainEvent

MONDAY = datetime(2026, 8, 3, tzinfo=timezone.utc)
CUSTOMERS = {"keith": "Keith Doyle", "beth": "Beth Pritchard"}


def shifts(weeks=4):
    history: list[DomainEvent] = []
    for day in range(7 * weeks):
        date = MONDAY + timedelta(days=day)
        for hour in range(8, 19):
            at = date.replace(hour=hour)
            working = date.weekday() in {0, 1, 3, 4} and 10 <= hour < 16
            history += repair_job_events(history, at, at_work=working, customers=CUSTOMERS)
    return history


def _at(event):
    return datetime.fromisoformat(event.payload["simulated_at"])


def test_jobs_come_in_get_done_and_get_collected_only_on_shift() -> None:
    history = shifts()
    kinds = [e.kind for e in history]
    assert kinds.count(TAKEN) >= 5 and kinds.count(FINISHED) >= 4 and kinds.count(COLLECTED) >= 2
    assert SETBACK in kinds
    for event in history:
        at = _at(event)
        assert at.weekday() in {0, 1, 3, 4} and 10 <= at.hour < 16
    # Never more than three jobs on the go.
    open_count = 0
    for event in history:
        open_count += (event.kind == TAKEN) - (event.kind == FINISHED)
        assert open_count <= 3
    memories = [e.payload["text"] for e in history if e.kind == "memory.recorded"]
    assert any("brought in" in m for m in memories)
    assert any("came back for" in m for m in memories)
    assert len(set(memories)) > 0.8 * len(memories)  # not the same note over and over


def test_a_part_on_order_holds_the_job_up() -> None:
    history = shifts(6)
    for setback in (e for e in history if e.kind == SETBACK and e.payload.get("waiting_until")):
        until = datetime.fromisoformat(setback.payload["waiting_until"])
        later = [
            e for e in history
            if e.kind == WORKED and e.payload["job_id"] == setback.payload["job_id"]
            and _at(e) > _at(setback)
        ]  # fmt: skip
        assert all(_at(e) >= until for e in later)
        if later:
            assert later[0].payload.get("part_arrived")


def test_he_gets_quicker_with_practice() -> None:
    history = shifts(8)
    taken = [e.payload for e in history if e.kind == TAKEN]
    from eidos.application.repair_jobs import JOBS

    base = {job.item: job.hours for job in JOBS}
    ratios = [p["needs_hours"] / base[p["item"]] for p in taken]
    assert ratios[0] == 1.0 and min(ratios[-3:]) < 1.0


def test_nothing_happens_off_shift() -> None:
    assert repair_job_events([], MONDAY.replace(hour=11), at_work=False) == []


def test_the_bench_as_he_thinks_of_it() -> None:
    history = shifts(1)
    at = _at(history[-1])
    bench = bench_view(history, at)
    assert bench and all(" for " in line or line.startswith("finished") for line in bench)
    assert len(bench) <= 4
    open_jobs = [j for j in jobs(history) if not j.collected]
    assert len(open_jobs) >= 1


def test_setbacks_annoy_him_and_finishing_pleases_him() -> None:
    history = shifts(4)
    names = {pid: name for pid, name in CUSTOMERS.items()}
    felt: set[str] = set()
    for event in history:
        if event.kind in {SETBACK, FINISHED}:
            upto = history[: history.index(event) + 1]
            felt |= {e.payload["kind"] for e in feeling_events(upto, _at(event), names=names)}
    assert {"irritation", "satisfaction"} <= felt
