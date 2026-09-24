"""Coming across the people of his town: a face, then a familiar face, then a name.

When Patrick is out somewhere public, awake and not already in a conversation, he now and
then notices one of the people who happen to be there. Who is there comes from the latent
town (``latent_town.py``); how they look to him is proposed on the fly by Firmament and
checked by rules. Seeing the same person again is recognition, and after a few sightings
they may get talking: Firmament proposes a name, what they do and their first words. From
then on they are someone he knows, with a relationship that grows through small talk. Only
someone who becomes a real friend is registered as a fully simulated resident, so the town
can hold thousands of people while the simulation carries only the ones who matter to him.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from time import perf_counter
from typing import Mapping, Sequence
from uuid import uuid4

from eidos.application.bonds import FRIENDLY, current_bonds
from eidos.application.experience import place_category
from eidos.application.latent_town import (
    LatentResident,
    pick,
    present_at,
    roll,
    townsfolk_number,
    works_here,
)
from eidos.application.place_discovery import FAR_AWAY
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.proposals import ProposalRejected
from eidos.domain.townsfolk import KINDS as TOWNSFOLK_KINDS
from eidos.domain.townsfolk import Townsperson, project_townsfolk
from eidos.domain.world_catalog import WorldCatalog
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest, ModelResponse

MAX_NOTICED_A_DAY = 2
INTRODUCTION_AFTER = 3  # sightings before they are likely to get talking
PROMOTION_HOUR = 21
_NAME = re.compile(r"^[A-Z][a-zA-Z'\-]+( [A-Z][a-zA-Z'\-]+){1,2}$")
_RESERVED = ("pathos", "patrick")
_COLOURS = ("#9b7e6b", "#7f9a8a", "#8c86a8", "#a8906a", "#6f8fa3", "#a37a7a", "#7d9468")


async def townsfolk_events(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    *,
    location_id: str,
    awake: bool,
    busy: bool,
    catalog: WorldCatalog,
    crowd: int,
    activity: str = "",
) -> list[DomainEvent]:
    """At most one person noticed, recognised, met or chatted with this hour."""
    if (
        not awake
        or busy
        or location_id in {"home", "in_transit", "in-transit", *FAR_AWAY}
        or location_id not in catalog.places
    ):
        return []
    today = at.date().isoformat()
    touched = [
        event
        for event in events_of(history, *TOWNSFOLK_KINDS)
        if str(event.payload.get("simulated_at", ""))[:10] == today
    ]
    if len(touched) >= MAX_NOTICED_A_DAY or any(
        event.payload.get("place_id") == location_id for event in touched
    ):
        return []
    category = place_category(location_id)
    # Someone promoted to a full resident is where their own simulated day takes them.
    here = [
        resident
        for resident in present_at(location_id, category, at)
        if resident.townsfolk_id not in catalog.people
    ]
    state = project_townsfolk(history)
    chance = min(0.3, 0.04 + 0.015 * max(0, crowd))
    if any(resident.townsfolk_id in state.people for resident in here):
        chance = max(chance, 0.35)  # a face you know catches your eye
    if roll("notice", location_id, at.isoformat()) >= chance:
        return []
    familiar = [resident for resident in here if resident.townsfolk_id in state.people]
    strangers = [resident for resident in here if resident.townsfolk_id not in state.people]
    if familiar and (not strangers or roll("familiar", location_id, at.isoformat()) < 0.6):
        # People gravitate to the faces they know best.
        known = max(
            familiar,
            key=lambda item: (
                roll("familiar-pick", item.townsfolk_id, at.isoformat())
                * (
                    1
                    + state.people[item.townsfolk_id].sightings
                    + 3 * state.people[item.townsfolk_id].chats
                ),
                item.townsfolk_id,
            ),
        )
        return await _meet_again(
            history,
            at,
            gateway,
            known,
            state.people[known.townsfolk_id],
            location_id,
            catalog,
        )
    stranger = pick(strangers, "stranger-pick", location_id, at.isoformat())
    if stranger is None:
        return []
    return await _notice(history, at, gateway, stranger, location_id, catalog, activity)


def townsfolk_promotion_events(
    history: Sequence[DomainEvent], at: datetime, catalog: WorldCatalog
) -> list[DomainEvent]:
    """A townsperson who has become a real friend becomes a fully simulated resident."""
    if at.hour != PROMOTION_HOUR:
        return []
    bonds = current_bonds(history)
    for person in project_townsfolk(history).acquaintances():
        if bonds.get(person.townsfolk_id) not in FRIENDLY:
            continue
        if person.townsfolk_id in catalog.people or person.name is None:
            continue
        haunt = person.places[0] if person.places else None  # where he first saw them
        if haunt is None or haunt not in catalog.places:
            continue
        number = townsfolk_number(person.townsfolk_id) or 0
        return [
            DomainEvent(
                "world.person_registered",
                "pathos",
                {
                    "proposal_id": f"townsfolk-promotion-{person.townsfolk_id}",
                    "entity_kind": "person",
                    "entity_id": person.townsfolk_id,
                    "name": person.name,
                    "purpose": person.occupation or f"a regular at {catalog.places[haunt].name}",
                    "description": person.description[0].upper() + person.description[1:],
                    "color": _COLOURS[number % len(_COLOURS)],
                    "location_id": haunt,
                    "origin": "townsfolk",
                    "simulated_at": at.isoformat(),
                },
                correlation_id=f"townsfolk-promotion-{person.townsfolk_id}",
            )
        ]
    return []


# -- one encounter --------------------------------------------------------------------


async def _notice(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    resident: LatentResident,
    location_id: str,
    catalog: WorldCatalog,
    activity: str,
) -> list[DomainEvent]:
    place = _mid_sentence(catalog.places[location_id].name)
    context = {
        "task": "glimpse",
        "time": at.isoformat(),
        "place": place,
        "place_kind": place_category(location_id),
        "what_people_are_doing": activity,
        "resident": {
            "age": resident.age_band,
            "usually_about": resident.rhythm,
            "role": "works here" if works_here(resident.number, location_id) else "visitor",
        },
        "seed": resident.number,
        "permission": (
            "Describe how this stranger looks to Patrick at a glance, as a short lowercase "
            "noun phrase beginning 'a' or 'an': appearance and what they are doing, e.g. "
            "'a woman in a paint-flecked jacket reading the notices'. If their role is 'works "
            "here', they are staff or always about the place. No name, no backstory, "
            "no private facts, nothing Patrick could not see."
        ),
    }
    output, content = await _ask(gateway, "glimpse", context, at, _GLIMPSE_SCHEMA)
    if content is None:
        return output
    try:
        description = _valid_description(content.get("description"))
    except ProposalRejected:
        return output
    noticed = DomainEvent(
        "townsfolk.noticed",
        "pathos",
        {
            "townsfolk_id": resident.townsfolk_id,
            "place_id": location_id,
            "description": description,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=f"townsfolk-{resident.townsfolk_id}",
    )
    return [*output, noticed, _memory(noticed, f"Noticed {description} at {place}.", at, 0.25)]


async def _meet_again(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    resident: LatentResident,
    person: Townsperson,
    location_id: str,
    catalog: WorldCatalog,
) -> list[DomainEvent]:
    place = _mid_sentence(catalog.places[location_id].name)
    common = {
        "townsfolk_id": resident.townsfolk_id,
        "place_id": location_id,
        "simulated_at": at.isoformat(),
        "owner": "pathos",
    }
    if person.name is not None:
        last_topic = next(
            (
                str(event.payload.get("topic"))
                for event in reversed(events_of(history, "townsfolk.chatted"))
                if event.payload.get("townsfolk_id") == person.townsfolk_id
            ),
            None,
        )
        return _chat(person, location_id, place, at, common, last_topic)
    attempt: list[DomainEvent] = []
    # The more often you see someone, the likelier you are to finally say hello.
    extra = max(0, person.sightings + 1 - INTRODUCTION_AFTER)
    ready = person.sightings + 1 >= INTRODUCTION_AFTER and roll(
        "introduce", resident.townsfolk_id, at.isoformat()
    ) < min(0.95, 0.25 + 0.4 * resident.sociability + 0.12 * extra)
    if ready:
        attempt = await _introduce(history, at, gateway, resident, person, place, common)
        if any(event.kind == "townsfolk.introduced" for event in attempt):
            return attempt
    seen = DomainEvent(
        "townsfolk.seen", "pathos", common, correlation_id=f"townsfolk-{resident.townsfolk_id}"
    )
    regular = location_id in person.places
    text = f"{person.description[0].upper()}{person.description[1:]} was at {place} again. " + (
        "They must be a regular." if regular else "Keep seeing them about."
    )
    return [*attempt, seen, _memory(seen, text, at, 0.2)]


async def _introduce(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    resident: LatentResident,
    person: Townsperson,
    place: str,
    common: Mapping[str, object],
) -> list[DomainEvent]:
    taken = sorted(_names_in_use(history))
    context = {
        "task": "introduction",
        "time": at.isoformat(),
        "place": place,
        "description": person.description,
        "times_seen": person.sightings + 1,
        "resident": {
            "age": resident.age_band,
            "district": resident.district.replace("-", " "),
            "role": "works here" if works_here(resident.number, person.places[0]) else "visitor",
        },
        "names_already_in_use": taken[-60:],
        "seed": resident.number,
        "permission": (
            "Patrick and this person have seen each other around and finally get talking. "
            "Give them a plausible ordinary British name not in names_already_in_use, what "
            "they do (a short lowercase phrase), and one natural first thing they say to him. "
            "They do not know his name yet. Nothing dramatic, no secrets, no claims about him."
        ),
    }
    output, content = await _ask(gateway, "introduction", context, at, _INTRODUCTION_SCHEMA)
    if content is None:
        return output
    try:
        name, occupation, first_words = _valid_introduction(content, set(taken))
    except ProposalRejected:
        return output
    introduced = DomainEvent(
        "townsfolk.introduced",
        "pathos",
        {**common, "name": name, "occupation": occupation, "first_words": first_words},
        correlation_id=f"townsfolk-{resident.townsfolk_id}",
    )
    text = (
        f"Finally got talking to {person.description} at {place}. {name}, {occupation}. "
        f'They said, "{first_words}"'
    )
    return [
        *output,
        introduced,
        _warmer(introduced, resident.townsfolk_id, at, 0.05, 0.02),
        _memory(introduced, text, at, 0.5, person_id=resident.townsfolk_id),
    ]


def _chat(
    person: Townsperson,
    location_id: str,
    place: str,
    at: datetime,
    common: Mapping[str, object],
    last_topic: str | None = None,
) -> list[DomainEvent]:
    first = (person.name or "them").split(" ")[0]
    topics = (
        "the weather and whether it'll hold",
        "a new sign going up on the high street",
        "how busy the place was",
        "nothing much, which was nice",
        "a film one of us half-remembered",
        "the price of everything",
        "a dog that kept trying to join in",
    )
    fresh = [item for item in topics if item != last_topic]
    topic = fresh[int(roll("topic", person.townsfolk_id, at.isoformat()) * len(fresh))]
    chatted = DomainEvent(
        "townsfolk.chatted",
        "pathos",
        {**common, "topic": topic},
        correlation_id=f"townsfolk-{person.townsfolk_id}",
    )
    return [
        chatted,
        _warmer(chatted, person.townsfolk_id, at, 0.05, 0.02),
        _memory(
            chatted,
            f"Bumped into {first} at {place}; we talked about {topic}.",
            at,
            0.3,
            person_id=person.townsfolk_id,
        ),
    ]


# -- Firmament -------------------------------------------------------------------------

_GLIMPSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["description"],
    "properties": {"description": {"type": "string", "maxLength": 140}},
}
_INTRODUCTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "occupation", "first_words"],
    "properties": {
        "name": {"type": "string", "maxLength": 40},
        "occupation": {"type": "string", "maxLength": 60},
        "first_words": {"type": "string", "maxLength": 200},
    },
}


async def _ask(
    gateway: ModelGateway,
    task: str,
    context: Mapping[str, object],
    at: datetime,
    schema: Mapping[str, object],
) -> tuple[list[DomainEvent], dict[str, object] | None]:
    request = ModelRequest(
        capability="firmament_townsfolk",
        task_version="1",
        temperature=0.9,
        max_output_tokens=160,
        output_schema=dict(schema),
        messages=(ModelMessage("user", json.dumps(context)),),
    )
    started = perf_counter()
    response: ModelResponse | None = None
    try:
        response = await asyncio.wait_for(gateway.generate(request), timeout=40)
        if response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "Townsfolk proposal was incomplete")
        content = json.loads(response.content)
        if not isinstance(content, dict):
            raise ProposalRejected("invalid_shape", "Townsfolk proposal must be an object")
    except (OSError, TimeoutError, TypeError, ValueError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
        return [_trace(task, "failed", at, started, response, gateway, code)], None
    return [_trace(task, "ok", at, started, response, gateway, None)], content


def _valid_description(value: object) -> str:
    text = " ".join(str(value or "").split()).rstrip(".")
    lowered = text.casefold()
    if not 10 <= len(text) <= 140 or not (lowered.startswith("a ") or lowered.startswith("an ")):
        raise ProposalRejected("invalid_description", "A glimpse is a short 'a …' phrase")
    if any(word in lowered for word in _RESERVED) or any(ch.isdigit() for ch in text):
        raise ProposalRejected("invalid_description", "A glimpse carries no names or numbers")
    return text[0].lower() + text[1:]


def _valid_introduction(content: Mapping[str, object], taken: set[str]) -> tuple[str, str, str]:
    name = " ".join(str(content.get("name", "")).split())
    occupation = " ".join(str(content.get("occupation", "")).split()).rstrip(".")
    first_words = " ".join(str(content.get("first_words", "")).split())
    if not _NAME.fullmatch(name) or name.casefold() in {item.casefold() for item in taken}:
        raise ProposalRejected("invalid_name", "An introduction needs a new, ordinary full name")
    if any(word in name.casefold() for word in _RESERVED):
        raise ProposalRejected("invalid_name", "That name is taken")
    if not 3 <= len(occupation) <= 60 or not 4 <= len(first_words) <= 200:
        raise ProposalRejected("invalid_introduction", "Occupation and first words are required")
    if any(word in first_words.casefold() for word in _RESERVED):
        raise ProposalRejected("invalid_introduction", "They don't know his name yet")
    return name, occupation[0].lower() + occupation[1:], first_words


def _mid_sentence(name: str) -> str:
    return "the " + name[4:] if name.startswith("The ") else name


def _names_in_use(history: Sequence[DomainEvent]) -> set[str]:
    from eidos.domain.world_catalog import project_world_catalog

    return {person.name for person in project_world_catalog(history).people.values()} | set(
        project_townsfolk(history).names().values()
    )


# -- events ----------------------------------------------------------------------------


def _warmer(
    source: DomainEvent, person_id: str, at: datetime, familiarity: float, trust: float
) -> DomainEvent:
    return DomainEvent(
        "relationship.changed",
        "pathos",
        {
            "person_id": person_id,
            "evidence_actor_id": "pathos",
            "familiarity_delta": familiarity,
            "trust_delta": trust,
            "reason": "Getting to know someone from around town.",
            "simulated_at": at.isoformat(),
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )


def _memory(
    source: DomainEvent,
    text: str,
    at: datetime,
    importance: float,
    *,
    person_id: str | None = None,
) -> DomainEvent:
    # An unnamed face is not yet someone he knows, so only named people carry person_id.
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "encounter",
            "source": "lived-townsfolk",
            "source_event_id": str(source.event_id),
            "townsfolk_id": source.payload.get("townsfolk_id"),
            "location_id": source.payload.get("place_id"),
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
            **({"person_id": person_id} if person_id else {}),
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )


def _trace(
    task: str,
    status: str,
    at: datetime,
    started: float,
    response: ModelResponse | None,
    gateway: ModelGateway,
    error_code: str | None,
) -> DomainEvent:
    return DomainEvent(
        "role.completed",
        "pathos",
        {
            "role": "firmament_townsfolk",
            "task": task,
            "status": status,
            "trace_id": str(uuid4()),
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "model": response.resolved_model if response else getattr(gateway, "model", "unknown"),
            "backend": response.backend if response else "unknown",
            "error_code": error_code,
            "simulated_at": at.isoformat(),
        },
    )


def townsfolk_names(history: Sequence[DomainEvent]) -> dict[str, str]:
    return project_townsfolk(history).names()
