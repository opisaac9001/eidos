"""How the things he chooses to do actually feel, and the tastes that grow out of that.

After each activity he chose, the rules settle how much he enjoyed it: whether it fits
what he values, whether he was short of company or too tired for it, the weather for
outdoor things, the small lift of somewhere new, a thing getting samey, the mood he
brought with him, and a share of plain unpredictability (a film can just be dull). A
strong experience, or a few that agree, becomes a taste. Later experiences can change his
mind. Nothing here is scripted by the model or fixed at the start: his tastes are earned.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from statistics import fmean
from typing import Mapping, Sequence

from eidos.application.place_discovery import HOME_GROUND
from eidos.application.work_rota import ROTA_PREFIX
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.state import PathosState
from eidos.domain.tastes import project_tastes
from eidos.domain.world_catalog import WorldCatalog

OUTDOORS = frozenset(
    {
        "park",
        "riverside",
        "hill-path",
        "nature-path",
        "dog-walk",
        "allotments",
        "churchyard",
        "cemetery",
        "sports-ground",
        "riverside-kiosk",
    }
)
MAKING = frozenset({"workshop", "hardware", "print-studio", "bike-repair"})
SOCIAL = frozenset(
    {"cafe", "crown-anchor", "market-hall", "community-hall", "music-room", "football-pavilion"}
)
CULTURE = frozenset(
    {"library", "cinema", "mill-museum", "reading-room", "secondhand", "charity-shop"}
)
ERRANDS = frozenset(
    {
        "post-office",
        "pharmacy",
        "launderette",
        "supermarket",
        "parcel-depot",
        "council-office",
        "clinic",
        "bus-interchange",
        "barber",
        "guesthouse",
        "station",
        "grocer",
        "bakery",
    }
)
# The value a kind of place speaks to.
CATEGORY_VALUE = {
    "outdoors": "autonomy",
    "making": "craft",
    "social": "care",
    "culture": "curiosity",
    "home": "autonomy",
}
LOVE_AT_ONCE = 0.65
SETTLED = 0.35
CHANGE_OF_HEART = 0.3


def place_category(place_id: str, action: str | None = None) -> str:
    if place_id == "home":
        return "making" if action == "work" else "home"
    for category, members in (
        ("outdoors", OUTDOORS),
        ("making", MAKING),
        ("social", SOCIAL),
        ("culture", CULTURE),
        ("errand", ERRANDS),
    ):
        if place_id in members:
            return category
    return "culture" if action == "learn" else "public"


def experience_events(
    history: Sequence[DomainEvent],
    realized: DomainEvent,
    state: PathosState,
    *,
    values: Mapping[str, float],
    traits: Mapping[str, float],
    weather: str,
    catalog: WorldCatalog,
) -> list[DomainEvent]:
    """Feel one realized activity once, and let it form or change a taste."""
    source_id = str(realized.event_id)
    if any(
        event.payload.get("source_event_id") == source_id
        for event in events_of(history, "experience.felt")
    ):
        return []
    payload = realized.payload
    if str(payload.get("schedule_id", "")).startswith(ROTA_PREFIX):
        # A shift is the job, not something he chose to spend his time on.
        return []
    at = datetime.fromisoformat(str(payload["simulated_at"]))
    place_id = str(payload.get("location_id") or "home")
    action = str(payload.get("action") or "")
    activity_type = str(payload.get("activity_type") or "activity")
    title = str(payload.get("title") or activity_type.replace("_", " "))
    category = place_category(place_id, action)
    social = category == "social" or isinstance(payload.get("companion_id"), str)
    parts: list[tuple[float, str, str]] = [(0.1, "", "")]  # (weight, if good, if bad)

    value_id = CATEGORY_VALUE.get(category)
    if value_id is not None:
        fit = 1.6 * (float(values.get(value_id, 0.7)) - 0.7)
        parts.append((fit, "it's the kind of thing that matters to me", "it isn't really me"))
    if social:
        want_company = float(traits.get("sociability", 0.52)) * (1 - state.connection)
        parts.append(
            (
                0.5 * want_company - 0.12,
                "it was good to be among people",
                "I'd rather have been on my own",
            )
        )
        if state.energy < 0.35:
            parts.append((-0.25, "", "I wasn't really up to company"))
    if category == "outdoors":
        lowered = weather.casefold()
        if any(word in lowered for word in ("rain", "storm", "snow", "sleet")):
            parts.append((-0.3, "", "the weather didn't help"))
        elif any(word in lowered for word in ("clear", "sun", "bright")):
            parts.append((0.12, "the weather was kind", ""))
    if category == "errand":
        parts.append((-0.15, "", "it was only an errand"))
    if state.energy < 0.3:
        parts.append((-0.2, "", "I was too tired to get much from it"))
    parts.append(
        (0.25 * state.valence, "I was in a good mood anyway", "I brought a low mood with me")
    )
    if place_id not in HOME_GROUND and _arrivals(history, place_id, before=at) <= 1:
        parts.append(
            (0.15 * float(traits.get("openness", 0.68)) / 0.68, "it was somewhere new", "")
        )
    recent_same = sum(
        1
        for event in events_of(history, "agency.activity_realized")
        if event.payload.get("activity_type") == activity_type
        and event is not realized
        and timedelta(0)
        <= at - datetime.fromisoformat(str(event.payload["simulated_at"]))
        <= timedelta(days=14)
    )
    if recent_same >= 4:
        parts.append((-0.15, "", "it's getting a bit samey"))
    texture = (_roll(f"felt:{source_id}") - 0.5) * 0.7
    parts.append((texture, "it was better than I expected", "it just didn't grab me"))

    enjoyment = round(max(-1.0, min(1.0, sum(weight for weight, _, _ in parts))), 2)
    reasons = [
        good if weight > 0 else bad
        for weight, good, bad in sorted(parts, key=lambda item: -abs(item[0]))
        if (weight > 0) == (enjoyment > 0) and abs(weight) >= 0.08 and (good if weight > 0 else bad)
    ][:2]
    felt = DomainEvent(
        "experience.felt",
        "pathos",
        {
            "source_event_id": source_id,
            "schedule_id": payload.get("schedule_id"),
            "place_id": place_id,
            "activity_type": activity_type,
            "category": category,
            "enjoyment": enjoyment,
            "reasons": "; ".join(reasons),
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        causation_id=realized.event_id,
        correlation_id=realized.correlation_id,
    )
    output = [felt]
    first_visit = any(text == "it was somewhere new" for _, text, _ in parts)
    doing = _gerund(title)
    if abs(enjoyment) >= 0.3 or first_visit:
        sentence = f"{doing}: {_verdict(enjoyment)}."
        if reasons:
            joined = " and ".join(reasons)
            sentence += f" {joined[0].upper()}{joined[1:]}."
        output.append(_memory(felt, sentence, at, importance=0.3 + 0.3 * abs(enjoyment)))
    subjects = [(f"activity:{activity_type}", doing[0].lower() + doing[1:], value_id)]
    if place_id != "home" and place_id in catalog.places:
        name = catalog.places[place_id].name
        name = "the " + name[4:] if name.startswith("The ") else name
        subjects.insert(0, (f"place:{place_id}", name, value_id))
    feelings = [*events_of(history, "experience.felt"), felt]
    tastes = project_tastes(history)
    for subject, label, subject_value in subjects:
        scores = [
            float(event.payload["enjoyment"])
            for event in feelings
            if _subject_matches(event, subject)
        ]
        taste = tastes.tastes.get(subject)
        change = _taste_change(
            scores,
            taste.stance if taste else None,
            taste.since if taste else None,
            feelings,
            subject,
        )
        if change is None:
            continue
        kind, stance = change
        text = (
            f"Changed my mind about {label}. "
            + ("Turns out I like it." if stance == "likes" else "It's lost its shine for me.")
            if kind == "taste.revised"
            else f"I think I've found something I love: {label}."
            if stance == "likes"
            else f"{label[0].upper()}{label[1:]}? Not for me, I've decided."
        )
        event = DomainEvent(
            kind,
            "pathos",
            {
                "subject": subject,
                "label": label,
                "stance": stance,
                "value_id": subject_value,
                "evidence_count": len(scores),
                "source_event_id": str(felt.event_id),
                "text": text,
                "simulated_at": at.isoformat(),
                "owner": "pathos",
            },
            causation_id=felt.event_id,
            correlation_id=f"taste-{subject}",
        )
        output += [event, _memory(event, text, at, importance=0.55)]
    return output


def taste_notes(history: Sequence[DomainEvent], catalog: WorldCatalog) -> dict[str, str]:
    """place -> how he has found it, in his words, for places he has a taste about."""
    notes: dict[str, str] = {}
    for taste in project_tastes(history).tastes.values():
        if taste.subject.startswith("place:"):
            notes[taste.subject.removeprefix("place:")] = (
                "somewhere he loves" if taste.stance == "likes" else "not really for him"
            )
    return notes


def _taste_change(
    scores: list[float],
    stance: str | None,
    since: datetime | None,
    feelings: Sequence[DomainEvent],
    subject: str,
) -> tuple[str, str] | None:
    if stance is None:
        if len(scores) == 1 and abs(scores[0]) >= LOVE_AT_ONCE:
            return "taste.formed", "likes" if scores[0] > 0 else "dislikes"
        recent = scores[-5:]
        if len(recent) >= 2 and abs(fmean(recent)) >= SETTLED:
            return "taste.formed", "likes" if fmean(recent) > 0 else "dislikes"
        return None
    later = [
        float(event.payload["enjoyment"])
        for event in feelings
        if _subject_matches(event, subject)
        and since is not None
        and datetime.fromisoformat(str(event.payload["simulated_at"])) > since
    ]
    if len(later) < 2:
        return None
    mood = fmean(later[-3:])
    if stance == "likes" and mood <= -CHANGE_OF_HEART:
        return "taste.revised", "dislikes"
    if stance == "dislikes" and mood >= CHANGE_OF_HEART:
        return "taste.revised", "likes"
    return None


def _subject_matches(event: DomainEvent, subject: str) -> bool:
    kind, _, value = subject.partition(":")
    key = "place_id" if kind == "place" else "activity_type"
    return event.payload.get(key) == value


def _arrivals(history: Sequence[DomainEvent], place_id: str, *, before: datetime) -> int:
    return sum(
        1
        for event in events_of(history, "pathos.moved")
        if event.payload.get("location_id") == place_id
        and datetime.fromisoformat(str(event.payload["simulated_at"])) <= before
    )


def _verdict(enjoyment: float) -> str:
    if enjoyment >= 0.6:
        return "loved it, honestly"
    if enjoyment >= 0.25:
        return "enjoyed it"
    if enjoyment > -0.25:
        return "fine, nothing special"
    if enjoyment > -0.6:
        return "didn't really enjoy it"
    return "not for me, I don't think"


_SECOND_VERBS = frozenset(
    {
        "have",
        "practise",
        "practice",
        "make",
        "watch",
        "write",
        "read",
        "sit",
        "draw",
        "listen",
        "take",
        "see",
        "walk",
        "talk",
        "get",
        "try",
        "look",
        "note",
        "sketch",
        "record",
        "compare",
        "collect",
        "keep",
    }
)
_DOUBLED = frozenset({"sit", "get", "put", "cut", "jog", "run", "set", "dig", "hop", "shop"})


def _gerund(title: str) -> str:
    """'Go along to the quiz' -> 'Going along to the quiz'."""
    first, _, rest = title.strip().partition(" ")
    word = first.lower()
    if word in _DOUBLED:
        word = word + word[-1] + "ing"
    elif word.endswith("ie"):
        word = word[:-2] + "ying"
    elif word.endswith("e") and not word.endswith("ee") and len(word) > 2:
        word = word[:-1] + "ing"
    elif not word.endswith("ing"):
        word += "ing"
    words = rest.split(" ")
    for index in range(len(words) - 1):
        if words[index] == "and" and words[index + 1].lower() in _SECOND_VERBS:
            words[index + 1] = _gerund(words[index + 1]).lower()
            break
    rest = " ".join(words)
    return f"{word[0].upper()}{word[1:]}{(' ' + rest) if rest else ''}"


def _roll(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def _memory(source: DomainEvent, text: str, at: datetime, *, importance: float) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "experience",
            "source": "lived-experience",
            "source_event_id": str(source.event_id),
            "owner": "pathos",
            "importance": round(min(0.9, importance), 2),
            "confidence": 1.0,
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )
