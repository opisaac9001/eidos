"""In the small hours his sense of his own life is brought up to date, and he talks from it."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from eidos.adapters.http_gateway import ROLE_FIELDS, ROLE_PROMPTS
from eidos.adapters.routed_gateway import CAPABILITIES, FALLBACKS
from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.application.life_lately import KIND, life_lately, life_lately_events
from eidos.domain.events import DomainEvent
from eidos.domain.proposals import STRUCTURED_CAPABILITIES

NIGHT = datetime(2026, 8, 27, 5, 0, tzinfo=timezone.utc)


def memory(text: str, hours_ago: float, importance: float = 0.6) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "importance": importance,
            "owner": "pathos",
            "simulated_at": (NIGHT - timedelta(hours=hours_ago)).isoformat(),
        },
    )


def test_once_a_night_while_he_sleeps_from_the_day_just_gone() -> None:
    history = [memory("Ellis showed me how to true a wheel.", 15), memory("Rang Mum.", 10)]
    gateway = StandInGateway()
    awake = asyncio.run(life_lately_events(history, NIGHT, gateway, asleep=False, names={}))
    assert awake == []
    made = asyncio.run(life_lately_events(history, NIGHT, gateway, asleep=True, names={}))
    assert [e.kind for e in made] == [KIND]
    assert "true a wheel" in life_lately(made)
    again = asyncio.run(
        life_lately_events(
            history + made, NIGHT + timedelta(hours=1), gateway, asleep=True, names={}
        )
    )
    assert again == []


def test_the_role_is_wired_for_real_models() -> None:
    assert "pathos_life_summary" in STRUCTURED_CAPABILITIES
    assert "pathos_life_summary" in CAPABILITIES and FALLBACKS["pathos_life_summary"]
    assert "pathos_life_summary" in ROLE_PROMPTS
    assert "the_day_just_gone" in ROLE_FIELDS["pathos_life_summary"]
    assert "my_life_lately" in ROLE_FIELDS["pathos"]


def test_he_talks_from_his_sense_of_his_life(tmp_path) -> None:
    class Capturing(StandInGateway):
        def __init__(self) -> None:
            self.requests = []

        async def generate(self, request):
            self.requests.append(request)
            return await super().generate(request)

    gateway = Capturing()
    store = SQLiteEventStore(tmp_path / "world.sqlite3")
    life = Life(store, gateway)
    life.advance(10)
    now = life.snapshot()["time"]
    summary = DomainEvent(
        KIND,
        "pathos",
        {"text": "Life's been quiet. I've been fixing a lot of lamps.", "simulated_at": now},
    )
    store.append("pathos", [summary], len(life.history()))
    life.request_visit("visit")
    life.chat("What've you been up to lately?", "turn")
    request = next(r for r in reversed(gateway.requests) if r.capability == "pathos")
    assert json.loads(request.messages[0].content)["my_life_lately"].startswith("Life's been quiet")
