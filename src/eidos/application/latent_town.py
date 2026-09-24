"""The rest of the town: thousands of people who exist without being stored.

Alderwick has about 8,500 residents. Each is a pure function of their number: roughly
how old they are, which district they live in, whether they are about in the morning, the
daytime or the evening, how sociable they are, which public places they frequent, and the
routine they keep there. None
of it is written down anywhere. When Patrick is somewhere, the handful of people plausibly
there that hour can be worked out, the same way every replay, and only someone he actually
notices is ever recorded (see ``application/townsfolk.py``). This is operator-side world
fact: it never reaches his cognition except through what he perceives.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from hashlib import sha256

TOWN_POPULATION = 8_500
PREFIX = "townsfolk-"

AGE_BANDS = (
    ("in their twenties", 0.18),
    ("in their thirties", 0.18),
    ("in their forties", 0.17),
    ("in their fifties", 0.16),
    ("in their sixties", 0.15),
    ("in their seventies", 0.11),
    ("elderly", 0.05),
)
RHYTHMS = {"morning": (7, 12), "daytime": (10, 17), "evening": (16, 23), "all day": (9, 21)}
DISTRICTS = ("old-town", "station-quarter", "westfield", "mill-quarter", "foundry", "southbank")
# How likely a resident is to be a regular somewhere, by the kind of place.
FREQUENTS = {
    "social": 0.02,
    "culture": 0.012,
    "errand": 0.03,
    "outdoors": 0.025,
    "making": 0.006,
    "public": 0.01,
}
SPECIFIC = {"supermarket": 0.08, "park": 0.04, "cafe": 0.02, "workshop": 0.004}
USUAL_DAY_CHANCE = 0.35  # each weekday is one of a regular's usual days with this chance
SKIPS = 0.15  # even a creature of habit misses one now and then
DROPS_IN = 0.03  # and sometimes turns up on a day they usually don't


@dataclass(frozen=True, slots=True)
class LatentResident:
    townsfolk_id: str
    number: int
    age_band: str
    rhythm: str
    district: str
    sociability: float


def _unit(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def townsfolk_id(number: int) -> str:
    return f"{PREFIX}{number}"


def townsfolk_number(identifier: str) -> int | None:
    if not identifier.startswith(PREFIX):
        return None
    tail = identifier.removeprefix(PREFIX)
    return int(tail) if tail.isdigit() and int(tail) < TOWN_POPULATION else None


@lru_cache(maxsize=None)
def latent_resident(number: int) -> LatentResident:
    if not 0 <= number < TOWN_POPULATION:
        raise ValueError("Nobody in town has that number")
    roll = _unit("age", number)
    age_band = AGE_BANDS[-1][0]
    for band, weight in AGE_BANDS:
        if roll < weight:
            age_band = band
            break
        roll -= weight
    rhythm = tuple(RHYTHMS)[int(_unit("rhythm", number) * len(RHYTHMS))]
    district = DISTRICTS[int(_unit("district", number) * len(DISTRICTS))]
    return LatentResident(
        townsfolk_id(number),
        number,
        age_band,
        rhythm,
        district,
        round(0.2 + 0.7 * _unit("sociability", number), 2),
    )


@lru_cache(maxsize=512)
def regulars(place_id: str, category: str) -> tuple[int, ...]:
    """Everyone in town who counts this place among their haunts."""
    chance = SPECIFIC.get(place_id, FREQUENTS.get(category, 0.03))
    return tuple(
        number for number in range(TOWN_POPULATION) if _unit("frequents", number, place_id) < chance
    )


def present_at(place_id: str, category: str, at: datetime) -> list[LatentResident]:
    """The regulars plausibly at a place this hour, the same on every replay.

    Regulars keep routines: their usual days and hour at a place, give or take the odd
    missed day or unplanned visit. That is why the same faces keep turning up.
    """
    day = at.date().isoformat()
    here: list[LatentResident] = []
    for number in regulars(place_id, category):
        usual = _unit("usual-day", number, place_id, at.weekday()) < USUAL_DAY_CHANCE
        chance = 1 - SKIPS if usual else DROPS_IN
        if _unit("visit", number, place_id, day) >= chance:
            continue
        resident = latent_resident(number)
        opens, closes = RHYTHMS[resident.rhythm]
        arrives = opens + int(_unit("usual-hour", number, place_id) * max(1, closes - opens - 1))
        stays = 1 + int(_unit("usual-stay", number, place_id) * 2)
        if arrives <= at.hour < arrives + stays:
            here.append(resident)
    return here


def pick(candidates: list[LatentResident], *salt: object) -> LatentResident | None:
    if not candidates:
        return None
    return candidates[int(_unit("pick", *salt) * len(candidates))]


def roll(*parts: object) -> float:
    return _unit("roll", *parts)
