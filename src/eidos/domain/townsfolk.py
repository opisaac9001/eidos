"""The townsfolk he has actually come across: faces first, then names.

The town holds thousands of people, but none of them exist in the record until Patrick
comes across one. A face noticed is recorded with how it looked to him; seeing it again is
recognition; getting talking gives a name. Only then do they become someone he knows, and
only a real friendship turns one into a fully simulated resident (see
``application/townsfolk.py``). Everything here is what Patrick perceived, never the latent
facts that decided who happened to be there.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

KINDS = ("townsfolk.noticed", "townsfolk.seen", "townsfolk.introduced", "townsfolk.chatted")


@dataclass(frozen=True, slots=True)
class Townsperson:
    townsfolk_id: str
    description: str
    first_seen_at: datetime
    last_seen_at: datetime
    last_place_id: str
    sightings: int = 1
    name: str | None = None
    occupation: str | None = None
    introduced_at: datetime | None = None
    chats: int = 0
    places: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TownsfolkState:
    people: dict[str, Townsperson] = field(default_factory=dict)

    def faces(self) -> list[Townsperson]:
        """People he'd recognise but hasn't been introduced to."""
        return [item for item in self.people.values() if item.name is None]

    def acquaintances(self) -> list[Townsperson]:
        return [item for item in self.people.values() if item.name is not None]

    def names(self) -> dict[str, str]:
        return {item.townsfolk_id: item.name for item in self.people.values() if item.name}


def project_townsfolk(history: Sequence[DomainEvent]) -> TownsfolkState:
    people: dict[str, Townsperson] = {}
    taken: set[str] = set()
    for event in events_of(history, *KINDS):
        p = event.payload
        townsfolk_id = str(p.get("townsfolk_id", ""))
        place_id = str(p.get("place_id", ""))
        at = datetime.fromisoformat(str(p["simulated_at"]))
        known = people.get(townsfolk_id)
        if event.kind == "townsfolk.noticed":
            description = str(p.get("description", "")).strip()
            if not townsfolk_id or known is not None or not description:
                raise ValueError("A face is noticed once, with how it looked")
            people[townsfolk_id] = Townsperson(
                townsfolk_id, description, at, at, place_id, places=(place_id,)
            )
            continue
        if known is None:
            raise ValueError("He can only recognise someone he has noticed before")
        places = known.places if place_id in known.places else (*known.places, place_id)
        seen = replace(
            known,
            last_seen_at=at,
            last_place_id=place_id,
            sightings=known.sightings + 1,
            places=places,
        )
        if event.kind == "townsfolk.introduced":
            name = str(p.get("name", "")).strip()
            if known.name is not None or not name or name.casefold() in taken:
                raise ValueError("An introduction gives one new, unused name")
            taken.add(name.casefold())
            seen = replace(
                seen,
                name=name,
                occupation=str(p.get("occupation", "")).strip() or None,
                introduced_at=at,
            )
        elif event.kind == "townsfolk.chatted":
            if known.name is None:
                raise ValueError("Small talk needs an introduction first")
            seen = replace(seen, chats=known.chats + 1)
        people[townsfolk_id] = seen
    return TownsfolkState(people)
