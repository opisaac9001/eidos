"""Residents have days of their own beyond work and home."""

from collections import Counter
from datetime import datetime, timedelta, timezone

from eidos.application.npc_movement import their_place_now
from eidos.application.resident_day import day_off, outing_now, outings

MONDAY = datetime(2026, 9, 7, tzinfo=timezone.utc)
SATURDAY = MONDAY + timedelta(days=5)
SUNDAY = MONDAY + timedelta(days=6)


def test_weekends_are_their_own_except_for_whoever_works_them() -> None:
    assert not day_off("stuart-hart", MONDAY)
    assert day_off("stuart-hart", SATURDAY) and day_off("stuart-hart", SUNDAY)
    # The café's open on Saturdays; Sunday is Mara's.
    assert not day_off("mara", SATURDAY) and day_off("mara", SUNDAY)
    assert (
        their_place_now("mara", "cafe", SUNDAY.replace(hour=9)) != "cafe"
        or outing_now("mara", "cafe", SUNDAY.replace(hour=9)) == "cafe"
    )


def test_over_a_month_people_get_out_and_about_and_differently() -> None:
    places: dict[str, Counter[str]] = {}
    for person in ("stuart-hart", "hannah-fenwick", "nina-vale", "beth-pritchard"):
        seen: Counter[str] = Counter()
        for day in range(28):
            for start, end, place in outings(person, "library", MONDAY + timedelta(days=day)):
                assert 9 <= start < end <= 23
                seen[place] += 1
        places[person] = seen
        assert sum(seen.values()) >= 6  # a few outings a week
    # Not everyone goes to the same places as often.
    assert len({tuple(sorted(seen.items())) for seen in places.values()}) > 1


def test_at_night_theyre_home() -> None:
    for day in range(14):
        night = (MONDAY + timedelta(days=day)).replace(hour=2)
        assert their_place_now("stuart-hart", "library", night) == "home"


def test_nobody_stays_in_the_cafe_after_it_shuts() -> None:
    from datetime import time

    hours = {"cafe": (time(7), time(18))}
    for day in range(60):
        for person in ("stuart-hart", "nina-vale", "townsfolk-8103"):
            for start, end, place in outings(
                person, "library", MONDAY + timedelta(days=day), hours
            ):
                if place == "cafe":
                    assert 7 <= start and end <= 18
