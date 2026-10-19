"""Small things happen to him because of where he is and what he's doing."""

from datetime import datetime, timedelta, timezone

from eidos.application.alertness import body_sensation_events
from eidos.application.happenings import HAPPENED, happening_events, phone_dead
from eidos.domain.events import DomainEvent

MORNING = datetime(2026, 8, 27, 9, 0, tzinfo=timezone.utc)


def went_out(at: datetime) -> DomainEvent:
    return DomainEvent(
        "pathos.travel_started",
        "pathos",
        {"simulated_at": (at - timedelta(minutes=20)).isoformat()},
    )


def happen(history, at, **situation):
    return happening_events(
        history,
        at,
        awake=situation.get("awake", True),
        location_id=situation.get("location_id", "workshop"),
        weather=situation.get("weather", "Clear"),
        alertness=situation.get("alertness", 0.9),
        at_work=situation.get("at_work", False),
        next_commitment=situation.get("next_commitment"),
    )


def test_rain_only_catches_him_when_he_goes_out_in_it() -> None:
    days = [MORNING + timedelta(days=n) for n in range(40)]
    soaked = [d for d in days if happen([went_out(d)], d, weather="Light rain")]
    assert soaked  # sometimes
    assert len(soaked) < 40  # not every time
    assert not any(happen([], d, weather="Light rain") for d in days)  # stayed in: dry
    assert not any(happen([went_out(d)], d, weather="Clear") for d in days)


def test_a_nicked_thumb_throbs_for_a_few_hours_after() -> None:
    hurt = DomainEvent(
        HAPPENED,
        "pathos",
        {"kind": "nicked_thumb", "text": "Chisel slipped.", "simulated_at": MORNING.isoformat()},
    )
    later = body_sensation_events(
        [hurt],
        MORNING + timedelta(hours=2),
        awake=True,
        location_id="workshop",
        hunger=0.2,
        weather="Clear",
    )
    assert [e.payload["sensation"] for e in later] == ["thumb"]


def test_a_dead_phone_stays_dead_until_its_charged() -> None:
    died = DomainEvent(
        HAPPENED,
        "pathos",
        {
            "kind": "phone_died",
            "simulated_at": MORNING.isoformat(),
            "until": (MORNING + timedelta(hours=2)).isoformat(),
        },
    )
    assert phone_dead([died], MORNING + timedelta(hours=1))
    assert not phone_dead([died], MORNING + timedelta(hours=3))


def test_no_more_than_a_couple_a_day_and_none_while_asleep() -> None:
    history: list = []
    for hour in range(8, 23):
        at = MORNING.replace(hour=hour)
        history += happen(
            [*history, went_out(at)], at, weather="Light rain", at_work=True, alertness=0.5
        )
    assert len([e for e in history if e.kind == HAPPENED]) <= 2
    assert happen([went_out(MORNING)], MORNING, weather="Light rain", awake=False) == []


def test_the_phone_doesnt_die_every_evening() -> None:
    history: list[DomainEvent] = []
    died = []
    for day in range(14):
        evening = MORNING.replace(hour=20) + timedelta(days=day)
        # A chatty day: plenty of messages.
        history += [
            DomainEvent(
                "chat.message", "pathos", {"text": "hi", "simulated_at": evening.isoformat()}
            )
            for _ in range(9)
        ]
        for hour in range(19, 23):
            at = evening.replace(hour=hour)
            out = happening_events(
                history, at, awake=True, location_id="home", weather="Cloudy",
                alertness=0.8, at_work=False, next_commitment=None,
            )  # fmt: skip
            history += out
            died += [at for e in out if e.kind == HAPPENED and e.payload["kind"] == "phone_died"]
    assert 0 < len(died) <= 2
    if len(died) == 2:
        assert died[1] - died[0] >= timedelta(days=10)
