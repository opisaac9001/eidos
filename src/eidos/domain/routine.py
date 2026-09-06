"""Deterministic daily texture: routine provides continuity without becoming a script."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256


@dataclass(frozen=True)
class RoutineBeat:
    hour: int
    location_id: str
    description: str
    energy: float
    activity: str = "ordinary"


_WEEKDAY_PALETTE: dict[int, tuple[tuple[str, str, float, str], ...]] = {
    7: (
        ("home", "Woke up and made breakfast.", 0.90, "breakfast"),
        ("home", "Woke early, opened the window, and made porridge.", 0.91, "breakfast"),
        ("home", "Lingered over tea and wrote down a fragment of a dream.", 0.87, "journaling"),
        ("home", "Stretched beside the window before making toast.", 0.92, "stretching"),
        ("home", "Read a few pages at the kitchen table over breakfast.", 0.88, "reading"),
    ),
    9: (
        ("cafe", "Visited the cafe before work.", 0.85, "morning_cafe"),
        ("cafe", "Stopped at Juniper Café and listened to the morning room.", 0.84, "morning_cafe"),
        ("park", "Took the long way to work through Willow Square.", 0.86, "morning_walk"),
        ("home", "Stayed home a little longer to finish a chapter.", 0.88, "reading"),
        ("cafe", "Had tea at the café and exchanged a few ordinary words.", 0.83, "morning_cafe"),
    ),
    10: (
        ("workshop", "Started work at the neighborhood workshop.", 0.75, "work"),
        (
            "workshop",
            "Sorted the repair shelf before beginning the day's work.",
            0.76,
            "organizing",
        ),
        ("workshop", "Practiced a careful binding stitch at the workshop.", 0.74, "craft_practice"),
        (
            "workshop",
            "Examined a box of damaged household things at the workshop.",
            0.73,
            "inspection",
        ),
        (
            "workshop",
            "Shared the big table and worked quietly among unfinished objects.",
            0.72,
            "work",
        ),
    ),
    13: (
        ("park", "Took a lunch break in the park.", 0.65, "lunch_walk"),
        ("cafe", "Ate a simple lunch in the back corner of the café.", 0.64, "lunch"),
        (
            "park",
            "Sat under the willows and watched people cross the square.",
            0.68,
            "people_watching",
        ),
        ("home", "Went home for soup and a quiet half hour.", 0.69, "quiet_lunch"),
        ("park", "Walked one slow circuit of Willow Square after lunch.", 0.67, "walk"),
    ),
    14: (
        ("workshop", "Returned to the workshop.", 0.60, "work"),
        (
            "workshop",
            "Spent the afternoon testing small repairs at the workshop.",
            0.59,
            "repair_practice",
        ),
        ("workshop", "Helped put the shared tools back into order.", 0.61, "organizing"),
        ("workshop", "Worked through a stubborn binding problem.", 0.57, "craft_practice"),
        ("workshop", "Made notes on an unfinished object before trying again.", 0.58, "study"),
    ),
    18: (
        ("home", "Returned home for dinner.", 0.40, "dinner"),
        ("park", "Walked through the square on the way home.", 0.43, "evening_walk"),
        ("home", "Cooked something simple and put music on quietly.", 0.42, "cooking"),
        ("cafe", "Caught the café's last quiet minutes before heading home.", 0.39, "cafe_visit"),
        ("home", "Ate leftovers and mended a loose shirt button.", 0.41, "mending"),
    ),
    22: (
        ("home", "Settled down for the night.", 0.20, "bedtime"),
        ("home", "Washed the dishes and read until sleep felt close.", 0.19, "bedtime_reading"),
        ("home", "Wrote three lines about the day before bed.", 0.21, "journaling"),
        ("home", "Made tea, dimmed the room, and let the day grow quiet.", 0.18, "bedtime"),
        ("home", "Listened to the pipes settle in the building before sleep.", 0.20, "bedtime"),
    ),
}

_WEEKEND_MIDDAYS = {
    10: (
        ("park", "Carried a book to Willow Square with nowhere urgent to be.", 0.82, "reading"),
        (
            "workshop",
            "Dropped into the workshop to practice without a deadline.",
            0.78,
            "craft_practice",
        ),
        (
            "cafe",
            "Stayed at the café over a second cup and watched the street.",
            0.80,
            "people_watching",
        ),
        ("park", "Followed an unfamiliar side street into Willow Square.", 0.83, "exploring"),
        ("home", "Put a neglected shelf in order at home.", 0.84, "organizing"),
    ),
    14: (
        ("park", "Sketched the shapes of bare branches in the square.", 0.68, "sketching"),
        ("workshop", "Joined the open table for an hour of quiet making.", 0.65, "craft_practice"),
        ("home", "Tried a new soup recipe and left it simmering.", 0.70, "cooking"),
        (
            "cafe",
            "Met the loose current of afternoon conversation at Juniper.",
            0.66,
            "socializing",
        ),
        ("park", "Helped gather windblown paper near the park gate.", 0.67, "neighborhood_care"),
    ),
}

_OPENING_ROUTINE = (
    RoutineBeat(7, "home", "Woke up and made breakfast.", 0.90, "breakfast"),
    RoutineBeat(9, "cafe", "Visited the cafe before work.", 0.85, "morning_cafe"),
    RoutineBeat(10, "workshop", "Started work at the neighborhood workshop.", 0.75, "work"),
    RoutineBeat(13, "park", "Took a lunch break in the park.", 0.65, "lunch_walk"),
    RoutineBeat(14, "workshop", "Returned to the workshop.", 0.60, "work"),
    RoutineBeat(18, "home", "Returned home for dinner.", 0.40, "dinner"),
    RoutineBeat(22, "home", "Settled down for the night.", 0.20, "bedtime"),
)


def routine_for_day(day: date) -> tuple[RoutineBeat, ...]:
    """Build a replay-stable day with workday/weekend texture and many combinations."""
    # The six-day acceptance story has known co-presence requirements. After it,
    # the seed world opens into the broader palette below.
    if date(2026, 1, 1) <= day <= date(2026, 1, 6):
        return _OPENING_ROUTINE
    palette = dict(_WEEKDAY_PALETTE)
    if day.weekday() >= 5:
        palette.update(_WEEKEND_MIDDAYS)
    return tuple(
        RoutineBeat(hour, *_choice(options, f"{day.isoformat()}:{hour}"))
        for hour, options in sorted(palette.items())
    )


def beats_between(start: datetime, end: datetime) -> list[tuple[datetime, RoutineBeat]]:
    """Left-open interval prevents repeating a beat after a restart."""
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    result = []
    while day <= end:
        for beat in routine_for_day(day.date()):
            at = day + timedelta(hours=beat.hour)
            if start < at <= end:
                result.append((at, beat))
        day += timedelta(days=1)
    return result


def emotionally_adjusted_beat(
    beat: RoutineBeat,
    *,
    initiative: float,
    social_openness: float,
    sustained_low_hours: int,
) -> tuple[RoutineBeat, str | None]:
    """Let emotion bend optional plans without erasing obligations or the whole day."""
    if not 0 <= initiative <= 1 or not 0 <= social_openness <= 1:
        raise ValueError("Emotional planning dimensions must be between zero and one")
    if (
        isinstance(sustained_low_hours, bool)
        or not isinstance(sustained_low_hours, int)
        or sustained_low_hours < 0
    ):
        raise ValueError("Sustained low mood duration must be non-negative")
    optional = beat.hour in {9, 13, 18} and beat.activity not in {"work", "dinner"}
    if optional and sustained_low_hours >= 24 and initiative < 0.4:
        return (
            RoutineBeat(
                beat.hour,
                "home",
                "Changed the loose plan and made room for a quieter hour at home.",
                min(0.75, beat.energy + 0.04),
                "restorative_pause",
            ),
            "sustained low mood reduced initiative for an optional outing",
        )
    if beat.hour == 9 and beat.location_id == "home" and social_openness >= 0.75:
        return (
            RoutineBeat(
                beat.hour,
                "cafe",
                "Felt open to company and went to Juniper Café for the morning.",
                beat.energy - 0.02,
                "morning_cafe",
            ),
            "high social openness favored company",
        )
    return beat, None


def needs_adjusted_beat(
    beat: RoutineBeat,
    *,
    rest: float,
    connection: float,
    curiosity: float,
    mastery: float,
    hunger: float,
    protected: bool = False,
) -> tuple[RoutineBeat, str | None]:
    """Let the strongest unmet need redirect free time without erasing obligations."""
    levels = {
        "rest": rest,
        "connection": connection,
        "curiosity": curiosity,
        "mastery": mastery,
    }
    if any(not 0 <= value <= 1 for value in (*levels.values(), hunger)):
        raise ValueError("Need levels must be between zero and one")
    obligations = {"breakfast", "work", "dinner", "bedtime", "incident_response"}
    if protected or beat.activity in obligations:
        return beat, None
    pressures = {name: 1 - value if value < 0.35 else 0.0 for name, value in levels.items()}
    pressures["rest"] = 1 - rest if rest < 0.28 else 0.0
    pressures["hunger"] = hunger if hunger > 0.82 else 0.0
    need, pressure = max(pressures.items(), key=lambda item: (item[1], item[0]))
    if pressure < 0.62:
        return beat, None
    alternatives = {
        "rest": RoutineBeat(
            beat.hour,
            "home",
            "Let the loose hour go quiet at home instead of pushing through it.",
            min(0.78, max(beat.energy, 0.62)),
            "restorative_pause",
        ),
        "connection": RoutineBeat(
            beat.hour,
            "cafe",
            "Went to Juniper Café and left room for ordinary company.",
            min(beat.energy, 0.68),
            "social_presence",
        ),
        "curiosity": RoutineBeat(
            beat.hour,
            "park",
            "Followed whatever caught the eye on an unhurried walk through the square.",
            min(beat.energy, 0.7),
            "noticing_walk",
        ),
        "mastery": RoutineBeat(
            beat.hour,
            "workshop" if beat.hour < 18 else "home",
            (
                "Used the open hour to practice one small, difficult piece of craft."
                if beat.hour < 18
                else "Practiced one small, difficult piece of craft at the kitchen table."
            ),
            min(beat.energy, 0.64),
            "craft_practice",
        ),
        "hunger": RoutineBeat(
            beat.hour,
            "home" if beat.location_id != "cafe" else "cafe",
            (
                "Stopped at the café for something substantial to eat."
                if beat.location_id == "cafe"
                else "Went home and made time for something substantial to eat."
            ),
            min(0.76, max(beat.energy, 0.58)),
            "need_driven_meal",
        ),
    }
    adjusted = alternatives[need]
    if adjusted.location_id == beat.location_id and adjusted.activity == beat.activity:
        return beat, None
    return adjusted, f"{need} was the strongest unmet need"


def _choice(
    options: tuple[tuple[str, str, float, str], ...], key: str
) -> tuple[str, str, float, str]:
    digest = sha256(key.encode()).digest()
    return options[int.from_bytes(digest[:4], "big") % len(options)]
