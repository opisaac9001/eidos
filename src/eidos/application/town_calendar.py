"""What's on in town: the ordinary weekly rhythm of public happenings.

These are fictional operating assumptions from the Alderwick design, not promises: some
weeks a happening is called off, and nothing obliges Patrick to go. A happening exists only
where its venue is in the world, and he only hears about happenings at places he knows,
the way you would from a noticeboard or from having been in. The calendar is derived, not
recorded, so it adds no events and changes nothing in the past.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Collection

from eidos.domain.world_catalog import WorldCatalog

CALLED_OFF_CHANCE = 0.12


@dataclass(frozen=True, slots=True)
class Happening:
    happening_id: str
    place_id: str
    weekday: int  # Monday is 0.
    starts_hour: int
    ends_hour: int
    title: str
    note: str
    weeks: str = "every"  # "every", "odd" or "even" ISO weeks.


WEEKLY: tuple[Happening, ...] = (
    Happening(
        "quiz",
        "crown-anchor",
        1,
        19,
        22,
        "Quiz night at the Crown",
        "Teams of four round the fire; somebody's always a person short.",
    ),
    Happening(
        "repair-cafe",
        "community-hall",
        3,
        18,
        21,
        "Repair café at the hall",
        "Bring something broken; volunteers help mend it over tea.",
        "even",
    ),
    Happening(
        "drawing-class",
        "community-hall",
        3,
        18,
        20,
        "Evening drawing class",
        "A patient teacher, cheap paper and a still life that never sits still.",
        "odd",
    ),
    Happening(
        "music-night",
        "music-room",
        4,
        19,
        22,
        "Friday music at the Listening Room",
        "Local players, a small crowd, and a hat passed round.",
    ),
    Happening(
        "friday-film",
        "cinema",
        4,
        19,
        22,
        "Friday film at the Regent",
        "An older film on the big screen, half the seats empty.",
    ),
    Happening(
        "market",
        "market-hall",
        5,
        9,
        13,
        "Saturday market",
        "Stalls round Market Court: veg, tools, bread, and people stopping to talk.",
    ),
    Happening(
        "allotment-morning",
        "allotments",
        6,
        10,
        13,
        "Allotment open morning",
        "Plot holders swapping seedlings and advice nobody asked for.",
    ),
    Happening(
        "sunday-league",
        "football-pavilion",
        6,
        10,
        12,
        "Sunday league on the Southbank",
        "Amateur football, a tea urn, and more shouting than skill.",
    ),
)


def whats_on(
    catalog: WorldCatalog,
    known_place_ids: Collection[str] | None,
    at: datetime,
    *,
    days: int = 3,
) -> list[dict[str, object]]:
    """Happenings from now to ``days`` ahead at places he knows (``None``: every place)."""
    upcoming: list[dict[str, object]] = []
    today = at.replace(hour=0, minute=0, second=0, microsecond=0)
    for offset in range(days + 1):
        day = today + timedelta(days=offset)
        week = day.isocalendar().week
        for item in WEEKLY:
            if (
                item.weekday != day.weekday()
                or item.place_id not in catalog.places
                or (known_place_ids is not None and item.place_id not in known_place_ids)
                or (item.weeks == "odd" and week % 2 == 0)
                or (item.weeks == "even" and week % 2 == 1)
            ):
                continue
            starts = day.replace(hour=item.starts_hour)
            ends = day.replace(hour=item.ends_hour)
            if ends <= at or starts > at + timedelta(days=days):
                continue
            occurrence = f"{item.happening_id}-{day.date().isoformat()}"
            upcoming.append(
                {
                    "happening_id": occurrence,
                    "title": item.title,
                    "place_id": item.place_id,
                    "place": catalog.places[item.place_id].name,
                    "starts_at": starts.isoformat(),
                    "ends_at": ends.isoformat(),
                    "note": item.note,
                    "called_off": called_off(occurrence),
                }
            )
    return sorted(upcoming, key=lambda entry: (str(entry["starts_at"]), str(entry["title"])))


def called_off(occurrence_id: str) -> bool:
    """Some weeks it just doesn't happen: the organiser's ill, the band cancels."""
    roll = int(sha256(f"called-off:{occurrence_id}".encode()).hexdigest()[:8], 16)
    return roll / 0xFFFFFFFF < CALLED_OFF_CHANCE


def happenings_now(catalog: WorldCatalog, at: datetime) -> dict[str, dict[str, object]]:
    """place -> the happening under way there this hour, for each one that is on."""
    return {
        str(item["place_id"]): item
        for item in whats_on(catalog, None, at, days=0)
        if not item["called_off"]
        and str(item["starts_at"]) <= at.isoformat() < str(item["ends_at"])
    }


def happening_opportunities(
    catalog: WorldCatalog, known_place_ids: Collection[str], at: datetime
) -> list[dict[str, object]]:
    """Happenings he could still make, soonest first, as noticed possibilities."""
    return [
        {
            "opportunity_id": f"happening-{item['happening_id']}",
            "kind": "public_happening",
            "text": f"{item['title']} ({_when(at, str(item['starts_at']))}). {item['note']}",
            "title": item["title"],
            "location_id": item["place_id"],
            "starts_at": item["starts_at"],
            "ends_at": item["ends_at"],
            "starts_in_hours": round(
                (datetime.fromisoformat(str(item["starts_at"])) - at).total_seconds() / 3600, 2
            ),
            "epistemic_status": "noticeboard",
            "action_authority": False,
        }
        for item in whats_on(catalog, known_place_ids, at, days=2)
        if not item["called_off"]
        and datetime.fromisoformat(str(item["starts_at"])) >= at + timedelta(hours=2)
    ]


def _when(at: datetime, starts_at: str) -> str:
    starts = datetime.fromisoformat(starts_at)
    day = (
        "today"
        if starts.date() == at.date()
        else "tomorrow"
        if starts.date() == (at + timedelta(days=1)).date()
        else starts.strftime("%A")
    )
    return f"{day} from {starts.hour:02d}:00"
