"""Two things he remembers, side by side, now and then make an idea worth keeping."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.daydreams import IDEA, daydream_events
from eidos.application.open_loops import FORMED
from eidos.domain.events import DomainEvent
from eidos.ports.model_gateway import ModelResponse


def memory(text: str, at: datetime) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {"text": text, "owner": "pathos", "importance": 0.6, "simulated_at": at.isoformat()},
    )


class Idea(StandInGateway):
    def __init__(self, idea: str, worth: int) -> None:
        self.idea, self.worth = idea, worth

    async def generate(self, request):
        if request.capability == "pathos_daydream":
            body = {"idea": self.idea, "kind": "photo", "worth": self.worth}
            return ModelResponse(json.dumps(body), "test", "test", "stop")
        return await super().generate(request)


def nights(gateway) -> list[DomainEvent]:
    found: list[DomainEvent] = []
    for n in range(10):
        night = datetime(2026, 9, 1 + n, 2, tzinfo=timezone.utc)
        history = [memory("Ellis showed me how to true a bike wheel.", night - timedelta(days=1))]
        found += asyncio.run(daydream_events(history, night, gateway, asleep=True))
    return found


def test_now_and_then_a_good_idea_becomes_something_he_means_to_do() -> None:
    kept = nights(Idea("I could photograph Ellis's hands truing the wheel.", 4))
    ideas = [e for e in kept if e.kind == IDEA]
    assert 1 <= len(ideas) < 10  # not every night
    loops = [e for e in kept if e.kind == FORMED]
    assert loops and loops[0].payload["text"] == "photograph Ellis's hands truing the wheel"
    assert any(
        e.kind == "memory.recorded" and e.payload["text"].startswith("Had an idea") for e in kept
    )


def test_weak_or_vague_ideas_are_let_go_but_kept_on_record() -> None:
    from eidos.application.daydreams import LET_GO

    weak = nights(Idea("I could photograph the wheel.", 2))
    assert weak and all(e.kind == LET_GO and e.payload["reason"] == "not good enough" for e in weak)
    vague = nights(Idea("I could explore something about wheels.", 5))
    assert vague and all(e.payload["reason"] == "too vague" for e in vague)


def test_only_while_he_sleeps_in_the_small_hours() -> None:
    night = datetime(2026, 9, 1, 2, tzinfo=timezone.utc)
    history = [memory("Ellis showed me how to true a bike wheel.", night - timedelta(days=1))]
    gateway = Idea("I could photograph Ellis's hands truing the wheel.", 5)
    assert asyncio.run(daydream_events(history, night, gateway, asleep=False)) == []
    assert asyncio.run(daydream_events(history, night.replace(hour=14), gateway, asleep=True)) == []
