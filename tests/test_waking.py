"""He drops off and wakes like a body, not a timetable: to the minute, and not the same
way every morning."""

from datetime import datetime, timedelta, timezone

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.inner_stream import stirring
from eidos.application.life import Life
from eidos.application.sleep_schedule import body_clock
from eidos.domain.state import PathosState

BED = datetime(2026, 8, 25, 23, tzinfo=timezone.utc)
WAKE = BED + timedelta(hours=8)


def nights(state: PathosState, first: datetime | None) -> list[dict]:
    return [body_clock(f"2026-08-{day:02d}", BED, WAKE, state, first) for day in range(1, 29)]


def test_on_a_work_morning_the_alarm_wakes_him_and_sometimes_he_snoozes() -> None:
    shift = WAKE + timedelta(hours=3)
    mornings = nights(PathosState(rest=0.6), shift)
    ups = [datetime.fromisoformat(m["up_at"]) for m in mornings]
    assert all(WAKE - timedelta(minutes=20) <= up <= WAKE + timedelta(minutes=18) for up in ups)
    assert all(up <= shift - timedelta(minutes=45) for up in ups)
    assert any(m["snoozes"] for m in mornings)
    assert any(m["waking"] == "just before the alarm" for m in mornings)
    assert len({up.minute for up in ups}) > 3  # not the same minute every day


def test_with_nowhere_to_be_he_sleeps_in() -> None:
    mornings = nights(PathosState(rest=0.6), None)
    ups = [datetime.fromisoformat(m["up_at"]) for m in mornings]
    assert all(up > WAKE for up in ups)
    assert any("lie-in" in m["waking"] for m in mornings)
    # Worn down, he sleeps in longer.
    tired = nights(PathosState(rest=0.3), None)
    assert sum((datetime.fromisoformat(m["up_at"]) - WAKE).seconds for m in tired) > sum(
        (up - WAKE).seconds for up in ups
    )


def test_a_worried_mind_sometimes_wakes_him_early() -> None:
    mornings = nights(PathosState(rest=0.6, arousal=0.75, valence=-0.3), None)
    early = [m for m in mornings if m["waking"].startswith("early")]
    assert early and all(datetime.fromisoformat(m["up_at"]) < WAKE for m in early)


def test_he_drops_off_around_bedtime_not_on_the_hour() -> None:
    asleep = [datetime.fromisoformat(m["asleep_at"]) for m in nights(PathosState(), None)]
    assert all(BED - timedelta(minutes=20) <= at <= BED + timedelta(minutes=30) for at in asleep)
    assert len({at.minute for at in asleep}) > 3


def test_his_mind_surfaces_in_the_half_hour_before_he_wakes() -> None:
    window = {
        "wake_at": WAKE.isoformat(),
        "up_at": (WAKE + timedelta(minutes=9)).isoformat(),
        "waking": "to the alarm, after snoozing",
    }
    view = {"pathos": {"awake": False}, "sleep_windows": [window]}
    assert stirring({**view, "time": (WAKE - timedelta(hours=1)).isoformat()}) is None
    before = stirring({**view, "time": (WAKE - timedelta(minutes=10)).isoformat()})
    assert before is not None and "the alarm going off; five more minutes" not in before["drifting"]
    snoozing = stirring({**view, "time": (WAKE + timedelta(minutes=4)).isoformat()})
    assert snoozing is not None and snoozing["drifting"] == [
        "the alarm going off; five more minutes"
    ]


def _night(life: Life):
    windows = [event for event in life.history() if event.kind == "sleep.window_selected"]
    return windows[-1].payload


def test_in_real_time_he_wakes_at_his_own_minute(tmp_path) -> None:
    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(21)  # into the evening, past choosing tonight's sleep
    night = _night(life)
    asleep_at = datetime.fromisoformat(night["asleep_at"])
    up_at = datetime.fromisoformat(night["up_at"])
    now = datetime.fromisoformat(life.snapshot()["time"])
    # The server steps to the exact minute he drops off...
    assert life.next_sleep_change() == asleep_at
    life.advance((asleep_at - now).total_seconds() / 3600)
    # (On the hour, the hourly step itself does it; either way it's his own minute.)
    assert life.settle_sleep() in {"sleep.started", None}
    assert not life.snapshot()["pathos"]["awake"]
    # ...and to the exact minute he comes to.
    assert life.next_sleep_change() == up_at
    life.advance((up_at - asleep_at).total_seconds() / 3600)
    assert life.settle_sleep() in {"sleep.ended", None}
    woke = next(e for e in reversed(life.history()) if e.kind == "sleep.ended")
    assert datetime.fromisoformat(woke.payload["simulated_at"]) == up_at
    assert woke.payload["reason"] == f"woke {night['waking']}"
    assert life.snapshot()["pathos"]["awake"]


def test_the_real_time_server_stops_at_the_minute_he_drops_off(tmp_path) -> None:
    from eidos.adapters.web_server import Runtime

    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(21)
    asleep_at = datetime.fromisoformat(_night(life)["asleep_at"])
    now = datetime.fromisoformat(life.snapshot()["time"])
    runtime = Runtime(life, interval=60)
    runtime.realtime_pending_seconds = (asleep_at - now).total_seconds() + 600
    runtime._commit_realtime_pending()
    dropped = next(e for e in reversed(life.history()) if e.kind == "sleep.started")
    assert datetime.fromisoformat(dropped.payload["simulated_at"]) == asleep_at
    runtime.close()
