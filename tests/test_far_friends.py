"""Friends who moved away: calls, and a weekend visit."""

from datetime import datetime, timedelta, timezone

from eidos.application.far_friends import far_friend_events, visit_fares
from eidos.domain.events import DomainEvent
from eidos.domain.world_catalog import project_world_catalog

MOVED = datetime(2027, 1, 10, 12, tzinfo=timezone.utc)


def months(days: int, depth: float, *, balance: int = 100_000, where=lambda at, h: "home"):
    history: list[DomainEvent] = []
    for hour in range(24 * days):
        at = MOVED + timedelta(hours=hour)
        history += far_friend_events(
            history,
            at,
            project_world_catalog(history),
            awake=True,
            location_id=where(at, history),
            away={"mara": ("Leeds", MOVED)},
            depths={"mara": depth},
            names={"mara": "Mara"},
            balance_pence=balance,
            rent_pence=12_500,
        )
    return history


def test_close_friends_keep_ringing_and_he_visits_once() -> None:
    history = months(300, 7.0)
    calls = [e for e in history if e.kind == "friend.kept_in_touch"]
    assert 4 <= len(calls) <= 25
    assert all(
        "her" in e.payload["text"] or "She" in e.payload["text"] or "Mara" in e.payload["text"]
        for e in calls
    )
    visits = [e for e in history if e.kind == "friend.visit_planned"]
    assert len(visits) == 1
    booking = next(e for e in history if e.kind == "schedule.created")
    assert booking.causation_id == visits[0].event_id
    starts = datetime.fromisoformat(booking.payload["starts_at"])
    assert starts.weekday() == 4 and booking.payload["location_id"] == "city-leeds"
    at = datetime.fromisoformat(visits[0].payload["simulated_at"])
    assert visit_fares(history, at)


def test_newer_friends_ring_less_and_are_not_visited() -> None:
    history = months(300, 4.5)
    calls = [e for e in history if e.kind == "friend.kept_in_touch"]
    close_calls = [e for e in months(300, 7.0) if e.kind == "friend.kept_in_touch"]
    assert len(calls) < len(close_calls)
    assert not any(e.kind == "friend.visit_planned" for e in history)


def test_no_visit_when_money_is_tight() -> None:
    assert not any(e.kind == "friend.visit_planned" for e in months(300, 7.0, balance=10_000))
