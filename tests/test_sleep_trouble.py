"""Lying awake: worry, money, or the night before something big."""

from datetime import datetime, timedelta, timezone

from eidos.application.sleep_trouble import restless_lately, sleep_trouble_events
from eidos.domain.events import DomainEvent

NIGHT = datetime(2027, 3, 1, 2, tzinfo=timezone.utc)


def nights(days, **kwargs):
    history: list[DomainEvent] = []
    options = {"asleep": True, "rest": 0.6, "valence": 0.2, "money_tight": False, "tomorrow": ()}
    options.update(kwargs)
    for day in range(days):
        history += sleep_trouble_events(history, NIGHT + timedelta(days=day), **options)
    return history


def restless(history):
    return [e for e in history if e.kind == "sleep.restless"]


def test_a_settled_life_sleeps_fine() -> None:
    assert nights(60) == []


def test_worry_keeps_him_up_some_nights_but_not_every_night() -> None:
    worried = restless(nights(56, valence=-0.5))
    assert 5 <= len(worried) <= 16  # at most two a week
    weeks = {}
    for event in worried:
        week = datetime.fromisoformat(event.payload["simulated_at"]).isocalendar()[:2]
        weeks[week] = weeks.get(week, 0) + 1
    assert max(weeks.values()) <= 2
    tired = [e for e in nights(56, valence=-0.5) if e.kind == "needs.changed"]
    assert tired and all(e.payload["rest"] < 0.6 for e in tired)


def test_money_worries_count_too() -> None:
    assert restless(nights(28, money_tight=True))


def test_the_night_before_something_big() -> None:
    history = sleep_trouble_events(
        [],
        NIGHT,
        asleep=True,
        rest=0.6,
        valence=0.3,
        money_tight=False,
        tomorrow=[("Moving day", "moving_house")],
    ) or sleep_trouble_events(
        [],
        NIGHT + timedelta(days=1),
        asleep=True,
        rest=0.6,
        valence=0.3,
        money_tight=False,
        tomorrow=[("Moving day", "moving_house")],
    )
    assert history and history[0].payload["why"] == "excited"
    assert restless_lately(history, NIGHT + timedelta(days=2)) == 1


def test_only_when_he_is_asleep_at_two() -> None:
    assert nights(28, valence=-0.5, asleep=False) == []
