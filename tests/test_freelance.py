"""He goes back to freelancing, as something that happens in his life, and it goes the way
freelancing goes: work through people who know him, quotes, his own hours, drafts and
feedback, invoices paid late and chased."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application import economy
from eidos.application.freelance import (
    ACCEPTED,
    CHASED,
    DELIVERED,
    ENQUIRY,
    LAST_SHIFT,
    LATE,
    OFFER,
    PAID,
    QUOTED,
    STARTED,
    TOLD,
    WORKED,
    _payments,
    jobs,
    work_view,
)
from eidos.application.life import Life
from eidos.application.work_rota import ROTA_PREFIX
from eidos.domain.events import DomainEvent


@pytest.fixture(scope="module")
def lived(tmp_path_factory) -> list[DomainEvent]:
    path = Path(tmp_path_factory.mktemp("freelance")) / "world.sqlite3"
    life = Life(SQLiteEventStore(path), StandInGateway())
    for _ in range(35):
        life.advance(24)
    return life.history()


def _at(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(
        str(event.payload.get("simulated_at") or "2000-01-01T00:00:00+00:00")
    )


def _first(history, kind):
    return next(e for e in history if e.kind == kind)


def test_going_freelance_happens_in_order_and_he_works_his_notice(lived) -> None:
    order = [_first(lived, kind) for kind in (OFFER, QUOTED, ACCEPTED, TOLD, STARTED)]
    assert [_at(e) for e in order] == sorted(_at(e) for e in order)
    ended = _first(lived, "work.agreement_ended")
    last_day = ended.payload["last_day"]
    # No shift after his last day was ever published, and the notice shifts were worked.
    shifts = [
        e for e in lived
        if e.kind == "schedule.created" and str(e.payload["schedule_id"]).startswith(ROTA_PREFIX)
        and _at(e) > _at(ended)
    ]  # fmt: skip
    assert not shifts
    assert _at(_first(lived, STARTED)).date().isoformat() > last_day
    assert any(e.kind == LAST_SHIFT for e in lived)
    # Telling Ellis took it off his mind.
    assert any(e.kind == "intention.done" and "Ellis" in str(e.payload.get("text")) for e in lived)


def test_the_work_comes_and_gets_done_in_his_own_hours(lived) -> None:
    worked = [e for e in lived if e.kind == WORKED]
    assert len(worked) >= 25
    # Daytime mostly; a late night only when a deadline's on top of him.
    assert not any(_at(e).hour < 8 for e in worked)
    assert sum(9 <= _at(e).hour <= 19 for e in worked) > 0.6 * len(worked)
    started = _at(_first(lived, STARTED))
    # Not a rota: the hours he puts in vary from day to day.
    per_day: dict[str, int] = {}
    for e in worked:
        if _at(e) > started:
            per_day[_at(e).date().isoformat()] = per_day.get(_at(e).date().isoformat(), 0) + 1
    assert len(set(per_day.values())) >= 2
    assert sum(1 for e in lived if e.kind == ENQUIRY) >= 2
    assert any(e.kind == DELIVERED for e in lived)
    # Half up front on the first contract, as income.
    deposit = next(e for e in lived if e.kind == PAID and e.payload.get("deposit"))
    assert economy._source_consequence(deposit)[0] == deposit.payload["fee_pence"] > 0


def test_no_wages_once_hes_left(lived) -> None:
    started = _at(_first(lived, STARTED))
    later = [
        e for e in lived
        if e.kind == "activity.completed" and str(e.payload.get("schedule_id", "")).startswith(ROTA_PREFIX)
        and _at(e) > started
    ]  # fmt: skip
    assert not later


AT = datetime(2026, 9, 7, 11, tzinfo=timezone.utc)


def _job(brief="leeds-api", late_chance_job="job-x", fee=35_000, terms_due=AT, deposit=0):
    def ev(kind, at, **p):
        return DomainEvent(
            kind, "pathos", {"job_id": late_chance_job, **p, "simulated_at": at.isoformat()}
        )

    return [
        ev(ENQUIRY, AT - timedelta(days=30), brief=brief, client="a small Leeds start-up"),
        ev(QUOTED, AT - timedelta(days=30), fee_pence=fee, reply_due=(AT - timedelta(days=29)).isoformat()),
        ev(ACCEPTED, AT - timedelta(days=29), fee_pence=fee, needed_hours=14,
           deadline=(AT - timedelta(days=15)).isoformat(), deposit_pence=deposit),
        ev(DELIVERED, AT - timedelta(days=16), pay_due=terms_due.isoformat()),
    ]  # fmt: skip


def test_an_invoice_is_paid_or_goes_late_and_gets_chased() -> None:
    outcomes = {"paid": 0, "late": 0}
    for n in range(60):
        history = _job(late_chance_job=f"job-{n}")
        out = _payments(jobs(history), AT, awake=True)
        if out[0].kind == PAID:
            outcomes["paid"] += 1
            continue
        assert out[0].kind == LATE
        outcomes["late"] += 1
        history += out
        # He chases it within a few working days, then it's paid.
        for hours in range(0, 24 * 10):
            at = AT + timedelta(hours=hours)
            step = _payments(jobs(history), at, awake=True)
            history += step
            if any(e.kind == PAID for e in step):
                break
        kinds = [e.kind for e in history]
        assert CHASED in kinds and PAID in kinds
        assert kinds.index(CHASED) < kinds.index(PAID)
    assert outcomes["paid"] > outcomes["late"] > 0


def test_what_he_has_on_as_he_would_say_it() -> None:
    history = _job(deposit=17_500)
    history.append(
        DomainEvent(PAID, "pathos", {"job_id": "job-x", "fee_pence": 17_500, "deposit": True,
                                     "simulated_at": (AT - timedelta(days=20)).isoformat()})
    )  # fmt: skip
    assert work_view(history, AT) == ["the API guide: done, invoice for £175 not paid yet"]
