"""Small touches of home and habit: a cat, the plants he keeps killing, and "the usual".

A life is mostly made of small, repeated things. Once he has moved somewhere that feels
like his own (or, if he never moves, after a year and a half of being settled), he may go
to the cat rescue "just to look" and come home with a cat. Lonelier and more caring, the
likelier. The cat has a name and a temperament of its own, fixed once and for good, and
from then on there are cat moments: a five o'clock wake-up, a cat sitting on whatever he's
reading, a leaf brought in as a present. They lift him a little. The cat costs him food
every week and, now and then, a vet's bill; when he goes home to Wye someone pops round to
feed it.

He buys a houseplant now and then, especially just after moving. When he's worn out or
away it goes unwatered, and it may die ("Another one. I'm a menace."). Sometimes one
survives three months and thrives, and that's a small, disproportionate pride.

And after enough visits to Juniper Café, Mara knows his order. One day she says "The
usual?", and from then on he has one. If he stays away for months, she either asks where
he's been or has forgotten, and he has to earn it again.

Everything is decided by replay-stable rolls on the date and the thing's id, and recorded
as ``pet.event``, ``plant.event`` and ``habit.regular``, each with a memory of it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, events_of

PET = "pet.event"
PLANT = "plant.event"
HABIT = "habit.regular"
AWAY_HOME = "wye-home"
CAFE = "cafe"

# -- the cat --
SETTLED_FOR = timedelta(days=540)  # if he never moves: after a year and a half
SETTLED_IN = timedelta(days=14)  # after a move, once the boxes are unpacked
ADOPT_CHANCE = 0.04  # per Sunday, scaled by how much he wants one (0 to 1)
ADOPTION_FEE_PENCE = 8_500
CAT_FOOD_PENCE = 850  # food and litter, each week
MOMENT_CHANCE = 0.07  # per evening at home
MOMENT_GAP = timedelta(days=4)
VET_CHANCE = 0.005  # per evening: a couple of vet visits a year
VET_GAP = timedelta(days=60)
AWAY_MENTION_GAP = timedelta(days=10)
SUNDAY_HOUR = 11
EVENING_HOUR = 20

NAMES = (
    "Moth",
    "Pickle",
    "Custard",
    "Bramble",
    "Kettle",
    "Sprocket",
    "Nutmeg",
    "Wren",
    "Pudding",
    "Marmalade",
)
LOOKS = (
    "a scruffy grey tabby",
    "a black cat with one white sock",
    "a ginger cat with a torn ear",
    "a tortoiseshell with a crooked tail",
    "a big black-and-white cat with a very small meow",
)
# temperament -> (how he'd describe it, a moment only this cat would have)
TEMPERAMENTS = {
    "aloof": (
        "aloof, and affectionate strictly on {their} own terms",
        "{name} ignored me all evening and then fell asleep on my feet. On {their} terms, as ever.",
    ),
    "lap": (
        "a lap cat who pretends not to be",
        "{name} spent an hour pretending not to want my lap, then gave up and took it. "
        "I didn't move till eleven.",
    ),
    "nervous": (
        "nervous of everyone but me",
        "Someone knocked on the door and {name} vanished under the bed for an hour. Came out "
        "when they'd gone and sat right next to me, like I'm the safe bit of the world.",
    ),
    "menace": (
        "a small menace with a big purr",
        "{name} knocked a screw off the table, watched it roll under the fridge, then looked "
        "at me like it was my fault.",
    ),
    "old_soul": (
        "an old soul who mostly follows the sun round the flat",
        "Watched {name} move from patch of sun to patch of sun all afternoon. There are worse "
        "ways to spend a Sunday. I joined in for a bit.",
    ),
}
MOMENTS = (
    "{name} woke me at five this morning by sitting on my chest and staring. Breakfast was, "
    "apparently, urgent.",
    "Sat down to read and {name} sat on the book. Not near it. On it. So that was my evening.",
    "Tried to fix a clock at the kitchen table. {name} sat on the instructions, then on the "
    "clock. We're sharing the table now, by which I mean I've given up.",
    "It rained all evening and {name} sat at the window watching it like it was telly. I "
    "watched {name} watching it. Not a bad evening, honestly.",
    "{name} brought a leaf in from outside and left it by my pillow like a present. I said "
    "thank you. I meant it.",
    "Came home worn out and {name} was waiting by the door, pretending not to be. Followed me "
    "round the flat until I sat down.",
    "{name} has decided the box the new kettle came in is the best thing I've ever bought. "
    "The kettle is a distant second.",
)
# (why, pence, how it went)
VET_VISITS = (
    ("{their} booster jabs", 4_500, "{They_are} fine, just deeply offended."),
    (
        "a limp that turned out to be nothing",
        6_000,
        "Sixty quid for nothing, and I'd pay it again.",
    ),
    ("something {they} ate", 9_500, "{They_are} fine now. My bank balance is less fine."),
    (
        "a scratched nose from a fight {they} definitely started",
        5_500,
        "The vet said '{They_are} a character'. I know.",
    ),
)

# -- houseplants --
PLANT_SETTLED = timedelta(days=60)
PLANT_CHANCE = 0.05  # per Saturday with no plant on trial; less once one has thrived
PLANT_CHANCE_AFTER_MOVE = 0.5  # the first Saturdays in a new place
NEW_PLACE_FOR = timedelta(days=35)
PLANT_AGAIN_AFTER_DEATH = timedelta(days=60)
WILTS = 0.05  # per week: even when he remembers
WILTS_NEGLECTED = 0.25  # per week he's worn out or away
THRIVES_AFTER = timedelta(weeks=10)
PLANT_HOUR = 12
# plant -> what he tells himself when he buys it
PLANTS = (
    ("spider plant", "They're meant to be unkillable."),
    ("peace lily", "It droops when it's thirsty, which seems fair."),
    ("fern", "The man at the market said ferns like a damp bathroom. I have one of those."),
    ("basil plant", "For cooking. Allegedly."),
    ("cactus", "You can't kill a cactus. Surely."),
    ("pothos", "Mostly for the name."),
)

# -- the usual --
USUAL_AFTER = 10  # visits on different days before they know his order
FORGET_AFTER = timedelta(days=100)  # away this long and it's "where've you been?" or forgotten
REMEMBERS = 0.5
LAPSED_AFTER = timedelta(days=60)
DRINKS = ("a flat white", "a pot of tea, strong", "a black coffee", "an oat latte")
FOOD = (
    "whatever the cheese scone situation is",
    "a cheese scone if there's one left",
    "a slice of the lemon drizzle",
    "a bacon roll on a Saturday",
)


def small_touches_due(at: datetime, *, awake: bool, location_id: str) -> bool:
    """Cheap test: could anything here happen this hour? (Checked before gathering inputs.)"""
    if not awake:
        return False
    if location_id == CAFE:
        return True
    if at.weekday() == 6 and at.hour >= SUNDAY_HOUR:
        return True
    return at.hour in {EVENING_HOUR, PLANT_HOUR}


def small_touches_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    location_id: str,
    connection: float,
    care: float,
    balance_pence: int,
    rent_pence: int,
    worn_out: bool = False,
    feeder: str | None = None,
) -> list[DomainEvent]:
    """This hour's small touch, if any: the cat, a plant, or being known at the café."""
    if not small_touches_due(at, awake=awake, location_id=location_id):
        return []
    return (
        _usual(history, at, location_id)
        or _cat(history, at, location_id, connection, care, balance_pence, rent_pence, feeder)
        or _plants(history, at, location_id, worn_out, balance_pence, rent_pence)
    )


# -- the cat -------------------------------------------------------------------------


def _cat(
    history: Sequence[DomainEvent],
    at: datetime,
    location_id: str,
    connection: float,
    care: float,
    balance_pence: int,
    rent_pence: int,
    feeder: str | None,
) -> list[DomainEvent]:
    pets = events_of(history, PET)
    adopted = next((e for e in pets if e.payload.get("kind") == "adopted"), None)
    if adopted is None:
        return _adopt(history, at, location_id, connection, care, balance_pence, rent_pence)
    if at.hour != EVENING_HOUR:
        return []
    if location_id == AWAY_HOME:
        return _fed_while_away(adopted, pets, at, feeder)
    if location_id != "home":
        return []
    return _vet(adopted, pets, at) or _moment(adopted, pets, at)


def _cat_eligible_since(history: Sequence[DomainEvent]) -> datetime | None:
    """After a move, once settled in; if he never moves, after a year and a half."""
    moves = events_of(history, "home.move")
    moved = [e for e in moves if e.payload.get("stage") == "moved"]
    if moved and moves[-1].payload.get("stage") == "moved":
        return _time(moved[-1]) + SETTLED_IN
    if moves:
        return None  # a move under way: not now
    opened = events_of(history, "finance.account_opened")
    return _time(opened[0]) + SETTLED_FOR if opened else None


def _adopt(
    history: Sequence[DomainEvent],
    at: datetime,
    location_id: str,
    connection: float,
    care: float,
    balance_pence: int,
    rent_pence: int,
) -> list[DomainEvent]:
    if at.weekday() != 6 or at.hour != SUNDAY_HOUR or location_id == AWAY_HOME:
        return []
    since = _cat_eligible_since(history)
    if since is None or at < since:
        return []
    if balance_pence < ADOPTION_FEE_PENCE + 2 * rent_pence:
        return []
    want = max(0.0, min(1.0, 0.5 * care + 0.5 * (1.0 - connection)))
    if _roll("adopt", at.date().isoformat()) >= ADOPT_CHANCE * want:
        return []
    pet_id = f"cat-{at.date().isoformat()}"
    name = NAMES[int(_roll("cat-name", pet_id) * len(NAMES))]
    look = LOOKS[int(_roll("cat-look", pet_id) * len(LOOKS))]
    temperament = sorted(TEMPERAMENTS)[int(_roll("cat-temperament", pet_id) * len(TEMPERAMENTS))]
    pronoun = "she" if _roll("cat-pronoun", pet_id) < 0.5 else "he"
    words = _pronouns(pronoun)
    nature = TEMPERAMENTS[temperament][0].format(**words)
    moved = [e for e in events_of(history, "home.move") if e.payload.get("stage") == "moved"]
    together = bool(moved and moved[-1].payload.get("partner_id"))
    rescue = "the cat rescue out past the allotments 'just to look'"
    opening = (
        f"We went to {rescue} and came home with {name}"
        if together
        else f"Went to {rescue}. Came home with {name}"
    )
    closing = (
        "I think I needed someone to come home to."
        if connection < 0.45
        else "The place feels different already. Warmer."
    )
    text = f"{opening}, {look}. {words['They_are']} {nature}. {closing}"
    return _record(
        PET,
        {
            "pet_id": pet_id,
            "kind": "adopted",
            "name": name,
            "look": look,
            "temperament": temperament,
            "nature": nature,
            "pronoun": pronoun,
            "fee_pence": ADOPTION_FEE_PENCE,
        },
        text,
        at,
        0.75,
        "milestone",
        "lived-pet",
        pet_id,
    )


def _moment(adopted: DomainEvent, pets: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    last = next((e for e in reversed(pets) if e.payload.get("kind") == "moment"), None)
    if last is not None and at - _time(last) < MOMENT_GAP:
        return []
    pet_id = str(adopted.payload["pet_id"])
    salt = (pet_id, at.date().isoformat())
    if _roll("moment", *salt) >= MOMENT_CHANCE:
        return []
    own = TEMPERAMENTS.get(str(adopted.payload.get("temperament")))
    pool = (*MOMENTS, own[1]) if own else MOMENTS
    words = {**_pronouns(str(adopted.payload.get("pronoun"))), "name": adopted.payload["name"]}
    pick = int(_roll("which-moment", *salt) * len(pool))
    text = pool[pick].format(**words)
    if last is not None and text == last.payload.get("text"):
        text = pool[(pick + 1) % len(pool)].format(**words)  # not the same thing twice running
    return _record(
        PET,
        {"pet_id": pet_id, "kind": "moment", "name": adopted.payload["name"]},
        text,
        at,
        0.35,
        "experience",
        "lived-pet",
        pet_id,
    )


def _vet(adopted: DomainEvent, pets: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    last = next((e for e in reversed(pets) if e.payload.get("kind") in {"vet", "adopted"}), None)
    if last is not None and at - _time(last) < VET_GAP:
        return []
    pet_id = str(adopted.payload["pet_id"])
    if _roll("vet", pet_id, at.date().isoformat()) >= VET_CHANCE:
        return []
    why, cost, how = VET_VISITS[
        int(_roll("vet-why", pet_id, at.date().isoformat()) * len(VET_VISITS))
    ]
    words = _pronouns(str(adopted.payload.get("pronoun")))
    name = adopted.payload["name"]
    text = f"Took {name} to the vet: {why.format(**words)}. £{cost // 100}. {how.format(**words)}"
    return _record(
        PET,
        {"pet_id": pet_id, "kind": "vet", "name": name, "cost_pence": cost},
        text,
        at,
        0.4,
        "experience",
        "lived-pet",
        pet_id,
    )


def _fed_while_away(
    adopted: DomainEvent, pets: Sequence[DomainEvent], at: datetime, feeder: str | None
) -> list[DomainEvent]:
    last = next((e for e in reversed(pets) if e.payload.get("kind") == "fed_while_away"), None)
    if last is not None and at - _time(last) < AWAY_MENTION_GAP:
        return []
    name = adopted.payload["name"]
    who = feeder.split()[0] if feeder else "The neighbour downstairs"
    text = (
        f"{who} is popping round to feed {name} while I'm in Wye. I left a list. It's a long "
        "list. Got a photo already: fed, unimpressed."
    )
    return _record(
        PET,
        {"pet_id": adopted.payload["pet_id"], "kind": "fed_while_away", "name": name},
        text,
        at,
        0.25,
        "experience",
        "lived-pet",
        str(adopted.payload["pet_id"]),
    )


def _pronouns(pronoun: str) -> dict[str, str]:
    if pronoun == "he":
        return {"they": "he", "their": "his", "They_are": "He's"}
    return {"they": "she", "their": "her", "They_are": "She's"}


# -- houseplants ---------------------------------------------------------------------


def _plants(
    history: Sequence[DomainEvent],
    at: datetime,
    location_id: str,
    worn_out: bool,
    balance_pence: int,
    rent_pence: int,
) -> list[DomainEvent]:
    plants = events_of(history, PLANT)
    latest = plants[-1] if plants else None
    on_trial = latest is not None and latest.payload.get("stage") == "bought"
    if on_trial:
        assert latest is not None
        return _water_or_not(history, latest, at, location_id, worn_out)
    if at.weekday() != 5 or at.hour != PLANT_HOUR or location_id == AWAY_HOME:
        return []
    opened = events_of(history, "finance.account_opened")
    if not opened or at - _time(opened[0]) < PLANT_SETTLED:
        return []
    if (
        latest is not None
        and latest.payload.get("stage") == "died"
        and at - _time(latest) < PLANT_AGAIN_AFTER_DEATH
    ):
        return []
    cost = 400 + round(800 * _roll("plant-cost", at.date().isoformat()))
    if balance_pence < cost + rent_pence + 3_000:
        return []
    moved = [e for e in events_of(history, "home.move") if e.payload.get("stage") == "moved"]
    new_place = bool(moved) and at - _time(moved[-1]) < NEW_PLACE_FOR
    thriving = sum(1 for e in plants if e.payload.get("stage") == "thriving")
    chance = PLANT_CHANCE_AFTER_MOVE if new_place else PLANT_CHANCE / (1 + 0.5 * thriving)
    if _roll("plant", at.date().isoformat()) >= chance:
        return []
    plant, excuse = PLANTS[int(_roll("which-plant", at.date().isoformat()) * len(PLANTS))]
    plant_id = f"plant-{at.date().isoformat()}"
    text = (
        f"Bought a {plant} for the new place. {excuse} This one's going to live."
        if new_place
        else f"Bought a {plant} from the market. {excuse} This one's going to live."
    )
    return _record(
        PLANT,
        {"plant_id": plant_id, "plant": plant, "stage": "bought", "cost_pence": cost},
        text,
        at,
        0.25,
        "experience",
        "lived-plant",
        plant_id,
    )


def _water_or_not(
    history: Sequence[DomainEvent],
    bought: DomainEvent,
    at: datetime,
    location_id: str,
    worn_out: bool,
) -> list[DomainEvent]:
    """Each Sunday he's home, the plant has either made it through the week or it hasn't."""
    if at.weekday() != 6 or at.hour < SUNDAY_HOUR or location_id != "home":
        return []
    plant_id, plant = str(bought.payload["plant_id"]), str(bought.payload["plant"])
    if at - _time(bought) >= THRIVES_AFTER:
        text = (
            f"The {plant} has put out new leaves. Actual new growth. I've kept something alive "
            "for nearly three months and I'm unreasonably proud of it."
        )
        return _record(
            PLANT,
            {"plant_id": plant_id, "plant": plant, "stage": "thriving"},
            text,
            at,
            0.45,
            "accomplishment",
            "lived-plant",
            plant_id,
        )
    if at - _time(bought) < timedelta(days=6):
        return []
    last_away = _visits(history).last_away
    away = last_away is not None and at - last_away < timedelta(days=7)
    week = at.isocalendar()
    wilts = WILTS_NEGLECTED if worn_out or away else WILTS
    if _roll("wilt", plant_id, f"{week.year}-W{week.week:02d}") >= wilts:
        return []
    why = (
        "I was in Wye and didn't think to ask anyone to water it."
        if away
        else "I've been too wiped out to remember it exists."
        if worn_out
        else "I honestly don't know what I did wrong."
    )
    text = f"The {plant} has died. {why} Another one. I'm a menace."
    return _record(
        PLANT,
        {"plant_id": plant_id, "plant": plant, "stage": "died"},
        text,
        at,
        0.3,
        "experience",
        "lived-plant",
        plant_id,
    )


# -- the usual -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Visits:
    """The days he's been to the café, and when he last arrived home in Wye."""

    cafe_days: tuple[date, ...] = ()
    last_away: datetime | None = None


def _visit_step(state: _Visits, event: DomainEvent) -> _Visits:
    if event.kind != "pathos.moved":
        return state
    place, raw = event.payload.get("location_id"), event.payload.get("simulated_at")
    if not isinstance(raw, str):
        return state
    when = datetime.fromisoformat(raw)
    if place == CAFE and (not state.cafe_days or state.cafe_days[-1] != when.date()):
        return replace(state, cafe_days=(*state.cafe_days, when.date()))
    if place == AWAY_HOME:
        return replace(state, last_away=when)
    return state


_VISITS: IncrementalFold[_Visits] = IncrementalFold(_Visits, _visit_step)


def _visits(history: Sequence[DomainEvent]) -> _Visits:
    return _VISITS(history)


def usual_order() -> str:
    """His order, once he has one: the same him, whichever café era it is."""
    drink = DRINKS[int(_roll("usual-drink") * len(DRINKS))]
    food = FOOD[int(_roll("usual-food") * len(FOOD))]
    return f"{drink} and {food}"


def _usual(history: Sequence[DomainEvent], at: datetime, location_id: str) -> list[DomainEvent]:
    if location_id != CAFE:
        return []
    today = at.date()
    habits = events_of(history, HABIT)
    latest = habits[-1] if habits else None
    if latest is not None and _time(latest).date() == today:
        return []
    days = _visits(history).cafe_days
    known = latest is not None and latest.payload.get("stage") in {"known", "welcomed_back"}
    order = usual_order()
    if known:
        before = [day for day in days if day < today]
        if not before or today - before[-1] < FORGET_AFTER:
            return []
        if _roll("remembers", today.isoformat()) < REMEMBERS:
            drink = order.split(" and ")[0]
            stage = "welcomed_back"
            text = (
                "Went back to Juniper Café after months away. Mara said 'Where've you been?' "
                f"and started on {drink} before I'd sat down. Nice to be missed."
            )
            importance = 0.45
        else:
            stage = "forgotten"
            text = (
                "Went into Juniper Café for the first time in ages. Mara asked what I'd like, "
                "same as anyone. Fair enough. I'll have to earn the usual again."
            )
            importance = 0.3
    else:
        since = _time(latest).date() if latest is not None else None
        count = sum(1 for day in days if since is None or day > since)
        if today not in days:
            count += 1  # he's here now, however he came to be
        if count < USUAL_AFTER:
            return []
        stage = "known"
        text = (
            "Walked into Juniper Café and Mara said 'The usual?' before I'd opened my mouth. "
            f"{order[0].upper()}{order[1:]}. I'm a regular somewhere. I didn't know I wanted "
            "that until it happened."
        )
        importance = 0.5
    return _record(
        HABIT,
        {"place_id": CAFE, "stage": stage, "order": order},
        text,
        at,
        importance,
        "experience",
        "lived-habit",
        f"usual-{CAFE}",
    )


# -- shared --------------------------------------------------------------------------


def _record(
    kind: str,
    payload: dict[str, object],
    text: str,
    at: datetime,
    importance: float,
    category: str,
    source: str,
    correlation_id: str,
) -> list[DomainEvent]:
    event = DomainEvent(
        kind,
        "pathos",
        {**payload, "text": text, "simulated_at": at.isoformat(), "owner": "pathos"},
        correlation_id=correlation_id,
    )
    memory = DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": category,
            "source": source,
            "source_event_id": str(event.event_id),
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
        },
        causation_id=event.event_id,
        correlation_id=correlation_id,
    )
    return [event, memory]


def small_touches_costs(
    history: Sequence[DomainEvent], at: datetime, *, awake: bool
) -> list[tuple[str, int, str]]:
    """(spend id, pence, what): the cat's food each Saturday, and recent one-off costs."""
    output: list[tuple[str, int, str]] = []
    pets = events_of(history, PET)
    adopted = next((e for e in pets if e.payload.get("kind") == "adopted"), None)
    if adopted is not None and at.weekday() == 5 and at.hour >= 11 and awake:
        week = at.isocalendar()
        output.append(
            (
                f"cat-food-{week.year}-W{week.week:02d}",
                CAT_FOOD_PENCE,
                f"Food and litter for {adopted.payload['name']}",
            )
        )
    for event in reversed(pets):
        if at - _time(event) > timedelta(days=2):
            break
        kind, name = event.payload.get("kind"), event.payload.get("name")
        if kind == "adopted":
            output.append(
                (
                    f"adoption-{event.payload['pet_id']}",
                    int(event.payload["fee_pence"]),
                    f"Adoption fee at the cat rescue, and a bed {name} will ignore",
                )
            )
        elif kind == "vet":
            output.append(
                (
                    f"vet-{event.payload['pet_id']}-{_time(event).date().isoformat()}",
                    int(event.payload["cost_pence"]),
                    f"Vet's bill for {name}",
                )
            )
    for event in reversed(events_of(history, PLANT)):
        if at - _time(event) > timedelta(days=2):
            break
        if event.payload.get("stage") == "bought":
            output.append(
                (
                    str(event.payload["plant_id"]),
                    int(event.payload["cost_pence"]),
                    f"A {event.payload['plant']} from the market",
                )
            )
    return output


# -- what he'd say about it ------------------------------------------------------------


def at_home_context(history: Sequence[DomainEvent]) -> dict[str, object] | None:
    """The cat and the plants, as he'd describe them."""
    pets = events_of(history, PET)
    adopted = next((e for e in pets if e.payload.get("kind") == "adopted"), None)
    plants = events_of(history, PLANT)
    if adopted is None and not plants:
        return None
    output: dict[str, object] = {}
    if adopted is not None:
        latest = next(
            (e for e in reversed(pets) if e.payload.get("kind") in {"moment", "vet"}), adopted
        )
        output["cat"] = {
            "name": str(adopted.payload["name"]),
            "what_they_look_like": str(adopted.payload["look"]),
            "what_they_are_like": str(adopted.payload["nature"]),
            "pronoun": str(adopted.payload["pronoun"]),
            "since": _time(adopted).date().isoformat(),
            "lately": str(latest.payload["text"]),
        }
    if plants:
        latest_plant = plants[-1]
        killed = sum(1 for e in plants if e.payload.get("stage") == "died")
        output["plants"] = {
            "thriving": [
                str(e.payload["plant"]) for e in plants if e.payload.get("stage") == "thriving"
            ],
            "touch_and_go": str(latest_plant.payload["plant"])
            if latest_plant.payload.get("stage") == "bought"
            else None,
            "killed_so_far": killed,
            "how_he_sees_it": "a menace to houseplants; any survivor is a small point of pride"
            if killed
            else None,
        }
    return output


def usual_context(history: Sequence[DomainEvent], at: datetime) -> str | None:
    """His usual at Juniper Café, if they know it."""
    habits = events_of(history, HABIT)
    if not habits or habits[-1].payload.get("stage") not in {"known", "welcomed_back"}:
        return None
    order = str(habits[-1].payload.get("order") or usual_order())
    days = _visits(history).cafe_days
    lapsed = bool(days) and at.date() - days[-1] >= LAPSED_AFTER
    return f"{order}, at Juniper Café; Mara starts on it when he walks in" + (
        ", though he hasn't been in for a while" if lapsed else ""
    )


def _time(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
