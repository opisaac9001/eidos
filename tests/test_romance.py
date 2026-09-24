"""Romance is rare, slow and uncertain; it can come to nothing, and never involves you."""

from datetime import datetime, timedelta, timezone

from eidos.application.romance import NEVER, SPARK_CHANCE, _roll, current_arc, romance_events
from eidos.domain.events import DomainEvent
from eidos.domain.selfhood import value_evidence

START = datetime(2026, 3, 2, 19, tzinfo=timezone.utc)
PLACES = frozenset({"home", "cafe", "park", "crown-anchor"})


def sparky(prefix: str = "townsfolk-") -> str:
    return next(f"{prefix}{n}" for n in range(500) if _roll("spark", f"{prefix}{n}") < SPARK_CHANCE)


def live(
    person: str, days: int, *, sociability: float = 0.9, ages=None, depths=None
) -> list[DomainEvent]:
    history: list[DomainEvent] = []
    calendar: dict[str, str] = {}
    for day in range(days):
        at = START + timedelta(days=day)
        output = romance_events(
            history,
            at,
            depths=depths if depths is not None else {person: 4.0, "user": 9.0, "ellis": 7.0},
            names={person: "Beth"},
            ages=ages or {},
            sociability=sociability,
            valence=0.3,
            awake=True,
            known_places=PLACES,
            calendar=calendar,
        )
        for event in output:
            if event.kind == "schedule.created":
                calendar[str(event.payload["schedule_id"])] = "scheduled"
        history += output
        # Every planned evening out actually happens.
        for schedule_id, status in list(calendar.items()):
            starts = datetime.fromisoformat(schedule_id[-10:] + "T19:00:00+00:00")
            if status == "scheduled" and at > starts:
                calendar[schedule_id] = "completed"
    return history


def test_it_never_involves_you_his_boss_or_family() -> None:
    assert {"user", "ellis", "mum", "dad", "tom"} <= NEVER
    history = live("nobody-sparky", 200)
    assert all(e.payload.get("person_id") not in NEVER for e in history)


def test_a_crush_can_become_dates_and_then_something_or_nothing() -> None:
    person = sparky()
    history = live(person, 400)
    stages = [
        e.payload["stage"]
        for e in history
        if e.kind == "romance.stage" and e.payload["person_id"] == person
    ]
    assert stages[0] == "drawn"
    assert stages[1] in {"seeing", "declined", "faded"}
    if stages[1] == "seeing":
        assert "date_planned" in stages and "date" in stages
        assert stages[-1] in {"date", "date_planned", "together", "ended", "broke_up"}
        dates = [e for e in history if e.kind == "schedule.created"]
        assert all(
            datetime.fromisoformat(e.payload["starts_at"]).weekday() in (4, 5) for e in dates
        )
        seeing = next(e for e in history if e.payload.get("stage") == "seeing")
        assert value_evidence(seeing)[0][:2] == ("care", 1)


def test_a_shy_patrick_mostly_lets_it_fade() -> None:
    faded = 0
    for n in range(8):
        person = sparky(f"shy-{n}-")
        history = live(person, 80, sociability=0.0)
        stages = [e.payload["stage"] for e in history if e.kind == "romance.stage"]
        faded += "faded" in stages
    assert faded >= 3


def test_older_townsfolk_are_not_candidates() -> None:
    person = sparky()
    history = live(person, 30, ages={person: "in their sixties"})
    assert current_arc(history) is None


def test_a_close_friend_sometimes_sets_him_up() -> None:
    history = live("nobody", 720, depths={"mara": 6.0, "user": 9.0})
    stages = [e.payload["stage"] for e in history if e.kind == "romance.stage"]
    assert "set_up" in stages or "passed_on" in stages
    set_up = [e for e in history if e.payload.get("stage") == "set_up"]
    for event in set_up:
        person = event.payload["person_id"]
        assert event.payload["matchmaker_id"] == "mara"
        introduced = [
            e
            for e in history
            if e.kind == "townsfolk.introduced" and e.payload["townsfolk_id"] == person
        ]
        assert len(introduced) == 1
        after = [
            e.payload["stage"]
            for e in history
            if e.kind == "romance.stage" and e.payload["person_id"] == person
        ]
        assert after[:2] == ["set_up", "date_planned"]
        assert len(after) < 4 or after[3] in {"seeing", "no_spark"}
    offers = [e for e in history if e.payload.get("stage") in {"set_up", "passed_on"}]
    times = [datetime.fromisoformat(e.payload["simulated_at"]) for e in offers]
    assert all(b - a >= timedelta(days=240) for a, b in zip(times, times[1:]))


def test_not_every_relationship_lasts() -> None:
    from eidos.application.romance import LONG_TERM

    couples = 0
    for n in range(60):
        person = f"townsfolk-{n}"
        if _roll("spark", person) >= SPARK_CHANCE or _roll("mutual", person) >= 0.5:
            continue
        stages = [
            e.payload["stage"]
            for e in live(person, 600, depths={person: 4.0})
            if e.kind == "romance.stage" and e.payload["person_id"] == person
        ]
        if "together" in stages:
            couples += 1
            assert ("broke_up" in stages) == (_roll("long-term", person) >= LONG_TERM)
    assert couples
