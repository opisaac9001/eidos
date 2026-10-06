"""The week and the season have a feel to them, from his calendar and the time of year."""

from datetime import date, datetime, timezone

from eidos.application.time_feel import how_it_feels, time_feel_events

# Work Monday, Tuesday, Thursday and Friday, as his rota has it.
WORK = {date(2026, 8, d) for d in (24, 25, 27, 28, 31)}


def feels(day: int, hour: int, *, month: int = 8, at_work: bool = False, money: int = 90_000):
    at = datetime(2026, month, day, hour, tzinfo=timezone.utc)
    return {
        kind
        for kind, _, _ in how_it_feels(at, work_days=WORK, balance_pence=money, at_work=at_work)
    }


def test_the_week_has_its_moods() -> None:
    assert "sunday_feeling" in feels(30, 20)  # Sunday evening, work in the morning
    assert "back_to_it" in feels(31, 8)  # Monday after the weekend
    assert "nearly_weekend" in feels(28, 15, at_work=True)  # Friday afternoon at the bench
    assert "day_off" in feels(26, 9)  # Wednesday off
    assert not feels(25, 15, at_work=True)  # an ordinary Tuesday afternoon


def test_the_season_and_the_money_have_theirs() -> None:
    assert "light_evening" in feels(26, 20)
    assert "dark_early" in feels(5, 17, month=11)
    assert "month_end" in feels(27, 12, money=12_000)


def test_each_is_felt_once_a_day() -> None:
    at = datetime(2026, 8, 30, 18, tzinfo=timezone.utc)
    shifts = [datetime(2026, 8, 31, 10, tzinfo=timezone.utc)]
    first = time_feel_events(
        [], at, awake=True, shift_starts=shifts, balance_pence=90_000, at_work=False
    )
    assert [e.payload["feeling"] for e in first] == ["sunday_feeling"]
    again = time_feel_events(
        first,
        at.replace(hour=19),
        awake=True,
        shift_starts=shifts,
        balance_pence=90_000,
        at_work=False,
    )
    assert again == []
