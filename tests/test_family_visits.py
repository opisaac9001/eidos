"""Weekends at home in Wye, and the night Mum rang about Dad."""

from datetime import date, datetime, timedelta, timezone

from eidos.application.economy import financial_foundation_events
from eidos.application.family import FAMILY_HOME
from eidos.application.family_visits import _scare_day, family_visit_events
from eidos.application.seasons import _easter
from eidos.application.work_rota import work_rota_events
from eidos.domain.events import DomainEvent
from eidos.domain.identity import identity_established_event
from eidos.domain.planning import project_planning
from eidos.domain.world_catalog import project_world_catalog

OPENED = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)


def visit(history, at, *, balance=150_000, location="home"):
    return family_visit_events(
        history,
        at,
        project_world_catalog(history),
        project_planning(history),
        awake=True,
        location_id=location,
        balance_pence=balance,
        rent_pence=12_500,
    )


def test_he_goes_home_for_easter_when_he_tells_mum_on_mothering_sunday() -> None:
    history = financial_foundation_events([], OPENED)
    mothering = _easter(2026) - timedelta(days=21)
    at = datetime(2026, mothering.month, mothering.day, 19, tzinfo=timezone.utc)
    agreed = visit(history, at)
    booking = next(e for e in agreed if e.kind == "schedule.created")
    starts = datetime.fromisoformat(booking.payload["starts_at"])
    ends = datetime.fromisoformat(booking.payload["ends_at"])
    assert starts.date() == _easter(2026) - timedelta(days=2)  # Good Friday
    assert ends.date() == _easter(2026) + timedelta(days=1)  # Easter Monday
    assert booking.payload["location_id"] == FAMILY_HOME
    assert booking.payload["activity_type"] == "visiting_home"
    assert visit([*history, *agreed], at + timedelta(hours=24)) == []


def test_when_money_is_too_tight_he_says_no_and_wishes_he_had_said_yes() -> None:
    history = financial_foundation_events([], OPENED)
    mothering = _easter(2026) - timedelta(days=21)
    at = datetime(2026, mothering.month, mothering.day, 19, tzinfo=timezone.utc)
    declined = visit(history, at, balance=5_000)
    assert not any(e.kind == "schedule.created" for e in declined)
    assert "too tight" in declined[0].payload["text"]


def test_the_august_bank_holiday_weekend() -> None:
    history = financial_foundation_events([], OPENED)
    monday = max(d for d in (date(2026, 8, n) for n in range(25, 32)) if d.weekday() == 0)
    agree = monday - timedelta(days=22)
    at = (
        datetime(2026, 8, agree.day, 19, tzinfo=timezone.utc)
        if agree.month == 8
        else (datetime(2026, agree.month, agree.day, 19, tzinfo=timezone.utc))
    )
    booking = next(e for e in visit(history, at) if e.kind == "schedule.created")
    assert datetime.fromisoformat(booking.payload["ends_at"]).date() == monday


def test_the_night_mum_rang_about_dad() -> None:
    history: list[DomainEvent] = [
        identity_established_event(OPENED.isoformat()),
        *financial_foundation_events([], OPENED),
    ]
    scare = _scare_day(history)
    assert scare is not None
    assert timedelta(days=430) <= scare - OPENED.date() <= timedelta(days=580)
    history += work_rota_events(
        history,
        project_planning(history),
        datetime.combine(scare, datetime.min.time(), OPENED.tzinfo),
    )
    night = datetime.combine(scare, datetime.min.time(), timezone.utc).replace(hour=20)
    output = visit(history, night)
    kinds = [e.kind for e in output]
    assert "family.contact" in kinds and "schedule.created" in kinds
    call = next(e for e in output if e.kind == "family.contact")
    assert "hospital" in call.payload["text"]
    booking = next(e for e in output if e.kind == "schedule.created")
    leaves = datetime.fromisoformat(booking.payload["starts_at"])
    assert leaves.date() == scare + timedelta(days=1) and leaves.hour == 9
    cancelled = [e for e in output if e.kind == "schedule.cancelled"]
    rota_days = {
        datetime.fromisoformat(entry.starts_at).date()
        for entry in project_planning(history).calendar.values()
        if entry.schedule_id.startswith("work-rota-")
    }
    away = {scare + timedelta(days=n) for n in range(1, 5)}
    assert cancelled and len(cancelled) == len(rota_days & away)
    history += output
    assert visit(history, night + timedelta(days=1)) == [] or all(
        e.kind != "schedule.created" for e in visit(history, night + timedelta(days=1))
    )
    # On the ward, the first afternoon.
    ward = (night + timedelta(days=1)).replace(hour=14)
    moment = visit(history, ward, location=FAMILY_HOME)
    assert moment and "ward" in moment[0].payload["text"]
    # A fortnight later Dad is on the mend.
    better = datetime.combine(scare + timedelta(days=14), datetime.min.time(), timezone.utc)
    news = visit(history, better.replace(hour=18))
    assert news and "porridge" in news[0].payload["text"]
