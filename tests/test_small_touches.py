"""Small touches of home and habit: a cat, the plants he kills, and "the usual"."""

from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import _standin_home_reply
from eidos.application.economy import financial_foundation_events
from eidos.application.small_touches import (
    ADOPTION_FEE_PENCE,
    CAT_FOOD_PENCE,
    MOMENT_GAP,
    NAMES,
    SETTLED_FOR,
    TEMPERAMENTS,
    USUAL_AFTER,
    at_home_context,
    small_touches_costs,
    small_touches_events,
    usual_context,
    usual_order,
)
from eidos.application.spending import spending_events
from eidos.domain.events import DomainEvent

OPENED = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
RENT = 12_500


def touch(history, at, *, location="home", lonely=True, balance=200_000, **kwargs):
    return small_touches_events(
        history,
        at,
        awake=True,
        location_id=location,
        connection=0.3 if lonely else 1.0,
        care=0.9 if lonely else 0.0,
        balance_pence=balance,
        rent_pence=RENT,
        **kwargs,
    )


def sundays(start_day: int, end_day: int):
    for day in range(start_day, end_day):
        at = (OPENED + timedelta(days=day)).replace(hour=11)
        if at.weekday() == 6:
            yield at


def live_sundays(history, start_day, end_day, **kwargs):
    for at in sundays(start_day, end_day):
        history += touch(history, at, **kwargs)
    return history


def of(history, kind, key="kind"):
    return [e.payload[key] for e in history if e.kind == kind]


def moved(at: datetime, stage: str = "moved") -> DomainEvent:
    return DomainEvent(
        "home.move",
        "pathos",
        {
            "move_id": "move-x",
            "stage": stage,
            "flat": "a flat",
            "weekly_rent_pence": 14_000,
            "text": "Moved.",
            "simulated_at": at.isoformat(),
        },
    )


def adopted_history(**kwargs):
    history = live_sundays(financial_foundation_events([], OPENED), 0, 1_500, **kwargs)
    assert "adopted" in of(history, "pet.event")
    return history


# -- the cat --------------------------------------------------------------------------


def test_no_cat_before_a_year_and_a_half_settled() -> None:
    history = adopted_history()
    adoption = next(e for e in history if e.kind == "pet.event")
    at = datetime.fromisoformat(adoption.payload["simulated_at"])
    assert at >= OPENED + SETTLED_FOR
    assert adoption.payload["name"] in NAMES
    assert adoption.payload["temperament"] in TEMPERAMENTS
    assert all(isinstance(v, (str, int, float, bool)) for v in adoption.payload.values())
    memory = history[history.index(adoption) + 1]
    assert memory.kind == "memory.recorded"
    assert memory.causation_id == adoption.event_id
    assert memory.payload["source_event_id"] == str(adoption.event_id)
    # One cat, for good.
    assert of(history, "pet.event").count("adopted") == 1


def test_the_cat_is_replay_stable() -> None:
    first = next(e for e in adopted_history() if e.kind == "pet.event")
    again = next(e for e in adopted_history() if e.kind == "pet.event")
    for key in ("pet_id", "name", "temperament", "look", "pronoun"):
        assert first.payload[key] == again.payload[key]


def test_no_cat_if_he_does_not_want_one_or_cannot_afford_it() -> None:
    history = financial_foundation_events([], OPENED)
    assert "adopted" not in of(live_sundays(list(history), 0, 1_500, lonely=False), "pet.event")
    assert "adopted" not in of(live_sundays(list(history), 0, 1_500, balance=20_000), "pet.event")


def test_after_moving_flat_the_cat_can_come_sooner_but_not_mid_move() -> None:
    start = financial_foundation_events([], OPENED)
    looking = [*start, moved(OPENED + timedelta(days=380), "looking")]
    assert "adopted" not in of(live_sundays(looking, 380, 900), "pet.event")
    history = [*start, moved(OPENED + timedelta(days=380))]
    history = live_sundays(history, 380, 540)
    adoption = next(e for e in history if e.kind == "pet.event")
    at = datetime.fromisoformat(adoption.payload["simulated_at"])
    assert OPENED + timedelta(days=394) <= at < OPENED + SETTLED_FOR


def test_the_cat_has_occasional_moments_at_home() -> None:
    history = adopted_history()
    adoption = next(e for e in history if e.kind == "pet.event")
    since = datetime.fromisoformat(adoption.payload["simulated_at"])
    name = adoption.payload["name"]
    for day in range(1, 181):
        at = (since + timedelta(days=day)).replace(hour=20)
        history += touch(history, at)
    moments = [e for e in history if e.kind == "pet.event" and e.payload["kind"] == "moment"]
    assert 4 <= len(moments) <= 30
    assert all(name in e.payload["text"] for e in moments)
    times = [datetime.fromisoformat(e.payload["simulated_at"]) for e in moments]
    assert all(b - a >= MOMENT_GAP for a, b in zip(times, times[1:]))
    # Nothing while he's out.
    out = (since + timedelta(days=200)).replace(hour=20)
    assert touch(history, out, location="crown-anchor") == []


def test_someone_feeds_the_cat_when_he_is_in_wye_mentioned_once() -> None:
    history = adopted_history()
    adoption = next(e for e in history if e.kind == "pet.event")
    since = datetime.fromisoformat(adoption.payload["simulated_at"])
    for day in range(30, 34):
        at = (since + timedelta(days=day)).replace(hour=20)
        history += touch(history, at, location="wye-home", feeder="Rowan Price")
    fed = [e for e in history if e.payload.get("kind") == "fed_while_away"]
    assert len(fed) == 1
    assert "Rowan" in fed[0].payload["text"]


def test_cat_food_is_charged_weekly_and_the_adoption_fee_once() -> None:
    history = adopted_history()
    adoption = next(e for e in history if e.kind == "pet.event")
    since = datetime.fromisoformat(adoption.payload["simulated_at"])
    costs = small_touches_costs(history, since + timedelta(hours=1), awake=True)
    assert (f"adoption-{adoption.payload['pet_id']}", ADOPTION_FEE_PENCE) in [
        (spend_id, pence) for spend_id, pence, _ in costs
    ]
    saturday = next(
        (since + timedelta(days=n)).replace(hour=12)
        for n in range(1, 8)
        if (since + timedelta(days=n)).weekday() == 5
    )
    spends = spending_events(
        history, saturday, awake=True, location_id="home", balance_pence=200_000
    )
    food = [e for e in spends if e.payload["spend_id"].startswith("cat-food-")]
    assert len(food) == 1
    assert food[0].payload["cost_pence"] == CAT_FOOD_PENCE
    assert food[0].payload["category"] == "everyday"
    # Bought once a week, not every hour of Saturday.
    later = spending_events(
        history + spends,
        saturday + timedelta(hours=2),
        awake=True,
        location_id="home",
        balance_pence=200_000,
    )
    assert not [e for e in later if e.payload["spend_id"].startswith("cat-food-")]
    # And no cat food before there's a cat.
    before = [e for e in history if e.kind != "pet.event"]
    assert not [c for c in small_touches_costs(before, saturday, awake=True) if "cat" in c[0]]


def test_the_cat_shows_in_his_self_context_and_the_stand_in_talks_about_it() -> None:
    history = adopted_history()
    adoption = next(e for e in history if e.kind == "pet.event")
    cat = at_home_context(history)["cat"]
    assert cat["name"] == adoption.payload["name"]
    assert cat["what_they_are_like"] == adoption.payload["nature"]
    context = {"identity": {"selfhood": {"at_home": {"cat": cat}}}}
    reply = _standin_home_reply("have you got any pets?", context)
    assert reply is not None and cat["name"] in reply
    no_cat = _standin_home_reply("do you have a cat?", {"identity": {"selfhood": {}}})
    assert no_cat is not None and "No pets" in no_cat
    assert _standin_home_reply("my cat is poorly", context) is None


# -- houseplants ----------------------------------------------------------------------


def test_plants_die_or_thrive_at_modest_rates() -> None:
    history = financial_foundation_events([], OPENED)
    years = 6
    for day in range(0, 365 * years):
        base = OPENED + timedelta(days=day)
        worn_out = (day // 7) % 3 == 0  # one week in three he's worn out
        for hour in (12, 11, 15):
            at = base.replace(hour=hour)
            history += touch(history, at, lonely=False, worn_out=worn_out)
    stages = of(history, "plant.event", "stage")
    bought, died, thriving = (stages.count(s) for s in ("bought", "died", "thriving"))
    assert bought >= years - 2  # he keeps trying
    assert died >= 2 and thriving >= 1
    assert 0.25 <= died / (died + thriving) <= 0.9
    assert len(stages) <= 7 * years  # a few plant events a year, not a saga
    died_text = next(e.payload["text"] for e in history if e.payload.get("stage") == "died")
    assert "I'm a menace" in died_text
    plants = at_home_context(history)["plants"]
    assert plants["killed_so_far"] == died
    reply = _standin_home_reply(
        "how are your plants doing?", {"identity": {"selfhood": {"at_home": {"plants": plants}}}}
    )
    assert reply is not None and ("killed" in reply or "thriving" in reply)
    assert not [e for e in history if e.kind == "pet.event"]


def test_away_in_wye_the_plant_is_likelier_to_die() -> None:
    def deaths(away: bool) -> int:
        history = financial_foundation_events([], OPENED)
        for day in range(0, 365 * 4):
            base = OPENED + timedelta(days=day)
            if away and day % 7 == 3:
                history.append(
                    DomainEvent(
                        "pathos.moved",
                        "pathos",
                        {"location_id": "wye-home", "simulated_at": base.isoformat()},
                    )
                )
            for hour in (12, 11):
                history += touch(history, base.replace(hour=hour), lonely=False)
        return of(history, "plant.event", "stage").count("died")

    assert deaths(away=True) > deaths(away=False)


# -- the usual ------------------------------------------------------------------------


def cafe_visit(history, at):
    history.append(
        DomainEvent(
            "pathos.moved",
            "pathos",
            {"location_id": "cafe", "simulated_at": at.isoformat()},
        )
    )
    for hour in range(2):
        history += touch(history, at + timedelta(hours=hour), location="cafe", lonely=False)
    return history


def test_the_usual_comes_once_after_enough_visits() -> None:
    history = financial_foundation_events([], OPENED)
    start = OPENED.replace(hour=10) + timedelta(days=30)
    for visit in range(USUAL_AFTER + 8):
        history = cafe_visit(history, start + timedelta(days=3 * visit))
        known = [e for e in history if e.kind == "habit.regular"]
        if visit < USUAL_AFTER - 1:
            assert known == []
    habits = [e for e in history if e.kind == "habit.regular"]
    assert [e.payload["stage"] for e in habits] == ["known"]
    assert "The usual?" in habits[0].payload["text"]
    assert habits[0].payload["order"] == usual_order()
    at = start + timedelta(days=3 * (USUAL_AFTER + 8))
    assert usual_context(history, at).startswith(usual_order())
    # Several visits in one day count once.
    same_day = financial_foundation_events([], OPENED)
    for hour in range(USUAL_AFTER + 2):
        same_day = cafe_visit(same_day, start + timedelta(hours=hour))
    assert not [e for e in same_day if e.kind == "habit.regular"]


def test_after_months_away_they_ask_where_he_has_been_or_have_forgotten() -> None:
    history = financial_foundation_events([], OPENED)
    start = OPENED.replace(hour=10) + timedelta(days=30)
    for visit in range(USUAL_AFTER):
        history = cafe_visit(history, start + timedelta(days=2 * visit))
    back = start + timedelta(days=2 * USUAL_AFTER + 150)
    assert "hasn't been in for a while" in usual_context(history, back)
    history = cafe_visit(history, back)
    stages = of(history, "habit.regular", "stage")
    assert stages[0] == "known"
    assert stages[1:] in (["welcomed_back"], ["forgotten"])
    assert (usual_context(history, back) is None) == (stages[-1] == "forgotten")
