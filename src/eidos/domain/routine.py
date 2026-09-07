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

_PLACE_TEXTURE: dict[str, tuple[str, ...]] = {
    "home": (
        "Light shifted slowly across the kitchen wall.",
        "The pipes clicked somewhere behind the plaster.",
        "A draft kept finding the edge of the table.",
        "The room held the faint smell of tea and old paper.",
        "Footsteps crossed the landing and faded downstairs.",
        "A patch of condensation blurred the lower window.",
        "The building settled around each small sound.",
    ),
    "cafe": (
        "Cups knocked softly together behind the counter.",
        "The front window clouded whenever the door closed.",
        "A chair scraped, then the room settled again.",
        "Someone near the door kept folding the same newspaper.",
        "The smell of toast briefly covered the smell of coffee.",
        "Rain-dark coats gathered along the wall hooks.",
        "A spoon turned slowly in an otherwise forgotten cup.",
    ),
    "workshop": (
        "Fine dust caught in the light above the shared bench.",
        "A loose window pane answered every passing lorry.",
        "The tool drawers never quite closed at the same angle.",
        "Someone had left a careful row of offcuts by the wall.",
        "The room smelled faintly of oil, paper, and damp wool.",
        "A clamp creaked whenever the bench shifted.",
        "Cold light rested on the metal edges of the tools.",
    ),
    "park": (
        "The willows moved before the rest of the trees noticed the wind.",
        "A bus sighed at the corner and pulled away again.",
        "Pigeons rearranged themselves around a dropped crust.",
        "The empty benches held small beads of rain.",
        "Cloud shadows crossed the paving faster than the people did.",
        "A paper receipt worried at the edge of the railings.",
        "Voices carried across the square and lost their words halfway.",
    ),
}

_MOMENT_TEXTURE = (
    "It made the hour feel briefly distinct from the rest of the day.",
    "The detail stayed in the background without asking to mean anything.",
    "Nothing important changed, but the moment did not feel interchangeable.",
    "It was the sort of detail that might be forgotten by evening.",
    "For a little while, attention rested there.",
)

_OPENING_ROUTINE = (
    RoutineBeat(7, "home", "Woke up and made breakfast.", 0.90, "breakfast"),
    RoutineBeat(9, "cafe", "Visited the cafe before work.", 0.85, "morning_cafe"),
    RoutineBeat(10, "workshop", "Started work at the neighborhood workshop.", 0.75, "work"),
    RoutineBeat(13, "park", "Took a lunch break in the park.", 0.65, "lunch_walk"),
    RoutineBeat(14, "workshop", "Returned to the workshop.", 0.60, "work"),
    RoutineBeat(18, "home", "Returned home for dinner.", 0.40, "dinner"),
    RoutineBeat(22, "home", "Settled down for the night.", 0.20, "bedtime"),
)

_OPENING_DESCRIPTIONS: dict[int, tuple[str, ...]] = {
    7: (
        "Woke up and made breakfast.",
        "Made breakfast, then stood by the open window with a second cup of tea.",
        "Took breakfast back to bed and read until the room warmed up.",
        "Made porridge for breakfast and wrote down the last bit of a strange dream.",
        "Burned the first slice of toast, laughed, and started breakfast again.",
        "Kept breakfast simple and spent a few quiet minutes watching the street wake up.",
    ),
    9: (
        "Visited the cafe before work.",
        "Took the corner table at Juniper Café and read the community noticeboard.",
        "Stopped at the café long enough to finish a cup of tea before work.",
        "Waited out a brief shower at Juniper Café before heading on.",
        "Shared the café window counter with the usual morning crowd.",
        "Picked up something warm at Juniper and stayed for one unhurried conversation.",
    ),
    10: (
        "Started work at the neighborhood workshop.",
        "Opened the workshop and sorted a tray of mismatched screws before the first repair.",
        "Spent the morning testing a loose chair joint at the workshop.",
        "Cleared yesterday's scraps from the shared bench and started a binding repair.",
        "Helped Ellis find the source of a faint rattle in an old desk drawer.",
        "Practiced a neater stitch on a damaged notebook before taking on other work.",
    ),
    13: (
        "Took a lunch break in the park.",
        "Ate lunch on the low wall in Willow Square and watched a dog chase leaves.",
        "Walked a slow lap of the square with lunch wrapped in paper.",
        "Found a dry bench in the park and spent lunch sketching passing coats.",
        "Shared the sunny end of a park bench with a stranger during lunch.",
        "Carried lunch through Willow Square and stopped to read a faded event poster.",
    ),
    14: (
        "Returned to the workshop.",
        "Went back to the workshop and sharpened two neglected hand tools.",
        "Returned to finish the chair joint after giving the glue time to settle.",
        "Spent the afternoon matching loose pages back to the right notebooks.",
        "Tested a stubborn drawer twice before admitting the runners needed replacing.",
        "Put the shared tools in order and finished one small repair before closing.",
    ),
    18: (
        "Returned home for dinner.",
        "Made soup for dinner and left the radio murmuring in the kitchen.",
        "Ate leftovers for dinner, then fixed a loose button at the table.",
        "Cooked too much pasta for dinner and packed the rest away for tomorrow.",
        "Had a late, simple dinner after stopping to watch the square lights come on.",
        "Made dinner from what was left in the cupboard and put music on quietly.",
    ),
    22: (
        "Settled down for the night.",
        "Washed the last mug, read for a while, and let sleep arrive on its own.",
        "Wrote a few uneven lines about the day before turning out the light.",
        "Made tea, opened the window for a minute, and went to bed early.",
        "Stayed up to finish one chapter, then left the book open beside the bed.",
        "Listened to the building settle around him and drifted off without setting an alarm.",
    ),
}


def routine_for_day(day: date) -> tuple[RoutineBeat, ...]:
    """Build a replay-stable day with workday/weekend texture and many combinations."""
    # The six-day acceptance story keeps stable co-presence windows, not repeated
    # lived content. Each day has distinct detail while retaining causal fixtures.
    if date(2026, 1, 1) <= day <= date(2026, 1, 6):
        day_index = (day - date(2026, 1, 1)).days
        return tuple(
            RoutineBeat(
                beat.hour,
                beat.location_id,
                _OPENING_DESCRIPTIONS[beat.hour][day_index],
                beat.energy,
                beat.activity,
            )
            for beat in _OPENING_ROUTINE
        )
    palette = dict(_WEEKDAY_PALETTE)
    if day.weekday() >= 5:
        palette.update(_WEEKEND_MIDDAYS)
    output = []
    for hour, options in sorted(palette.items()):
        location_id, description, energy, activity = _choice(options, f"{day.isoformat()}:{hour}")
        texture_index = day.toordinal() + hour * 11
        place_texture = _PLACE_TEXTURE[location_id][texture_index % 7]
        moment_texture = _MOMENT_TEXTURE[(texture_index // 7 + hour) % 5]
        output.append(
            RoutineBeat(
                hour,
                location_id,
                f"{description} {place_texture} {moment_texture}",
                energy,
                activity,
            )
        )
    return tuple(output)


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
