"""How awake he feels comes from his nights and the time of day, and his body speaks up
when there's a reason."""

from datetime import datetime, timedelta, timezone

from eidos.application.alertness import SENSED, alertness, body_sensation_events, nights
from eidos.domain.events import DomainEvent

DAY = datetime(2026, 8, 27, tzinfo=timezone.utc)


def slept(start: datetime, hours: float) -> list[DomainEvent]:
    return [
        DomainEvent("sleep.started", "pathos", {"simulated_at": start.isoformat()}),
        DomainEvent(
            "sleep.ended",
            "pathos",
            {"simulated_at": (start + timedelta(hours=hours)).isoformat()},
        ),
    ]


def test_the_day_has_a_shape_a_slump_and_a_second_wind() -> None:
    night = slept(DAY - timedelta(hours=1), 8)  # 23:00 to 07:00
    at = lambda hour: alertness(night, DAY.replace(hour=hour))  # noqa: E731
    assert at(10) > at(14)  # the after-lunch slump
    assert at(19) > at(15)  # a second wind
    assert at(23) < at(10)  # tired by bedtime


def test_a_short_night_leaves_him_duller_the_next_day() -> None:
    good = slept(DAY - timedelta(hours=1), 8)
    short = slept(DAY + timedelta(hours=2), 5)  # 02:00 to 07:00
    assert nights(short, DAY.replace(hour=12)) == [5.0]
    assert alertness(short, DAY.replace(hour=12)) < alertness(good, DAY.replace(hour=12))


def test_his_body_speaks_up_once_and_with_a_cause() -> None:
    history = slept(DAY + timedelta(hours=2), 5)
    morning = DAY.replace(hour=8)
    felt = body_sensation_events(
        history, morning, awake=True, location_id="home", hunger=0.2, weather="Clear"
    )
    assert [e.payload["sensation"] for e in felt] == ["heavy_head"]
    assert "5 hours" in felt[0].payload["text"]
    history += felt
    assert (
        body_sensation_events(
            history,
            morning + timedelta(hours=1),
            awake=True,
            location_id="home",
            hunger=0.2,
            weather="Clear",
        )
        == []
    )
    assert all(e.kind == SENSED for e in felt)


def test_he_knows_how_he_slept_last_night() -> None:
    from datetime import datetime, timedelta, timezone

    from eidos.application.alertness import last_night
    from eidos.domain.events import DomainEvent

    down = datetime(2026, 8, 28, 23, 40, tzinfo=timezone.utc)
    up = down + timedelta(hours=7, minutes=30)
    history = [
        DomainEvent("sleep.started", "pathos", {"simulated_at": down.isoformat()}),
        DomainEvent("sleep.ended", "pathos",
                    {"simulated_at": up.isoformat(), "reason": "woke to the alarm"}),
    ]  # fmt: skip
    told = last_night(history, up + timedelta(hours=3))
    assert (
        told
        == "Dropped off about 23:40, woke to the alarm at 07:10: about 7.5 hours, slept through."
    )
    restless = [
        DomainEvent(
            "sleep.restless", "pathos", {"simulated_at": (down + timedelta(hours=2)).isoformat()}
        )
    ]
    assert "restless" in last_night([*history, *restless], up + timedelta(hours=1))
    assert last_night(history, up + timedelta(days=2)) is None  # that's not last night
