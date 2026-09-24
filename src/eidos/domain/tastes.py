"""Tastes: what he has found, by living it, that he loves or that isn't for him.

A taste is about something specific (a place, a kind of activity), is earned from how
experiences actually felt, and can change when later experiences disagree. Changing his
mind is part of having a mind; the history of both stances is kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

STANCES = frozenset({"likes", "dislikes"})


@dataclass(frozen=True, slots=True)
class Taste:
    subject: str  # "place:<id>" or "activity:<activity_type>"
    label: str
    stance: str
    since: datetime
    value_id: str | None = None
    changed_mind: bool = False


@dataclass(frozen=True, slots=True)
class TasteState:
    tastes: dict[str, Taste] = field(default_factory=dict)

    def loves(self) -> list[Taste]:
        return [item for item in self.tastes.values() if item.stance == "likes"]

    def not_for_him(self) -> list[Taste]:
        return [item for item in self.tastes.values() if item.stance == "dislikes"]


def project_tastes(history: Sequence[DomainEvent]) -> TasteState:
    tastes: dict[str, Taste] = {}
    for event in events_of(history, "taste.formed", "taste.revised"):
        payload = event.payload
        subject = str(payload.get("subject", ""))
        stance = payload.get("stance")
        if not subject or stance not in STANCES:
            raise ValueError("A taste needs a subject and a stance")
        existing = tastes.get(subject)
        if event.kind == "taste.formed" and existing is not None:
            raise ValueError("A taste can only form once; later changes are revisions")
        if event.kind == "taste.revised" and (existing is None or existing.stance == stance):
            raise ValueError("A revision must change an existing taste's stance")
        value_id = payload.get("value_id")
        tastes[subject] = Taste(
            subject,
            str(payload.get("label", subject)),
            str(stance),
            datetime.fromisoformat(str(payload["simulated_at"])),
            str(value_id) if isinstance(value_id, str) else None,
            event.kind == "taste.revised",
        )
    return TasteState(tastes)
