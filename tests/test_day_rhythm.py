"""Things keep their rough place in his day without happening at the same hour every day."""

from datetime import date, timedelta

from eidos.application.day_rhythm import hour_today


def test_about_the_same_time_never_the_same_time() -> None:
    days = [date(2026, 8, 1) + timedelta(days=n) for n in range(30)]
    hours = [hour_today("news-evening", day, 18, 1, 2) for day in days]
    assert set(hours) <= {17, 18, 19, 20} and len(set(hours)) >= 3
    assert hours == [hour_today("news-evening", day, 18, 1, 2) for day in days]  # replayable
