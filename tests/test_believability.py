"""His recent life, measured against how people actually live."""

from datetime import datetime, timedelta, timezone

from eidos.application.believability import believability_report
from eidos.domain.events import DomainEvent

NOW = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)


def event(kind: str, at: datetime, **payload) -> DomainEvent:
    return DomainEvent(kind, "pathos", {"simulated_at": at.isoformat(), **payload})


def test_the_report_compares_him_with_people() -> None:
    history = []
    for day in range(7):
        morning = (NOW - timedelta(days=day)).replace(hour=7, minute=8 * day)
        history.append(event("sleep.ended", morning))
        history.append(event("schedule.created", morning, title=f"Thing {day}", actor_id="pathos"))
    thoughts = [("concern", "Should ring Rowan tomorrow."), ("here", "Kettle's on.")] * 5
    report = believability_report(history, NOW, thoughts=thoughts, stream_counts=(80, 20))
    assert report["mind_wandering"]["value"] == 0.5
    assert report["mind_wandering"]["verdict"] == "in the human range"
    assert report["thinking_ahead"]["value"] == 0.5
    assert report["days_alike"]["verdict"] == "varied"
    assert report["sleep"]["wake_spread_minutes"] > 0
    assert report["thoughts_turned_away"]["value"] == 0.2


def test_clockwork_sleep_is_called_out() -> None:
    history = [event("sleep.ended", (NOW - timedelta(days=d)).replace(hour=7)) for d in range(7)]
    assert believability_report(history, NOW)["sleep"]["verdict"] == "low"
