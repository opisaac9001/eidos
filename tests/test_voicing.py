"""His narrated life re-told in his words, keeping every fact."""

import asyncio
import json
from datetime import datetime, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.voicing import keeps_the_facts, voice_pending
from eidos.domain.events import DomainEvent
from eidos.ports.model_gateway import ModelGateway, ModelRequest, ModelResponse

AT = datetime(2027, 5, 1, 19, tzinfo=timezone.utc)
ORIGINAL = "Rowan's moving to Leeds. A job they couldn't turn down. I'm gutted, honestly."


class Scripted(ModelGateway):
    model = "scripted"

    def __init__(self, text: str) -> None:
        self.text = text
        self.calls = 0

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        return ModelResponse(json.dumps({"text": self.text}), "scripted", "test", "stop")


def lived() -> list[DomainEvent]:
    news = DomainEvent(
        "friend.life_event",
        "pathos",
        {"person_id": "rowan", "kind": "moving_announced", "text": ORIGINAL},
    )
    memory = DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": ORIGINAL,
            "source": "lived-friend-life",
            "source_event_id": str(news.event_id),
            "category": "relationship",
        },
        causation_id=news.event_id,
    )
    return [news, memory]


def test_a_retelling_must_keep_names_places_and_numbers() -> None:
    good = "Rowan told me they're off to Leeds. Job they couldn't say no to. Gutted, if I'm honest."
    assert keeps_the_facts(ORIGINAL, good)
    assert not keeps_the_facts(ORIGINAL, "Rowan's off to Manchester. Gutted.")  # place changed
    assert not keeps_the_facts(
        ORIGINAL, "Rowan and Sam are moving to Leeds. I'm gutted."
    )  # new name
    assert not keeps_the_facts("Paid £140 for the deposit.", "Paid £150 for the deposit today.")
    assert not keeps_the_facts(ORIGINAL, "Leeds.")  # too short


def test_a_good_retelling_replaces_the_memory_and_its_source_together() -> None:
    pending = lived()
    ids = [event.event_id for event in pending]
    retold = "Rowan told me they're off to Leeds. Job they couldn't say no to. Gutted, honestly."
    traces = asyncio.run(voice_pending(pending, 0, AT, Scripted(retold), mood="Low"))
    assert traces[0].payload["status"] == "ok"
    news, memory = pending
    assert memory.payload["text"] == retold and memory.payload["authored_text"] == ORIGINAL
    assert news.payload["text"] == retold
    assert [event.event_id for event in pending] == ids  # same events, new words


def test_a_retelling_that_changes_the_facts_is_dropped() -> None:
    pending = lived()
    traces = asyncio.run(
        voice_pending(pending, 0, AT, Scripted("Rowan and Sam are moving to York."), mood="Low")
    )
    assert traces[0].payload["error_code"] == "changed_facts"
    assert pending[1].payload["text"] == ORIGINAL and "authored_text" not in pending[1].payload


def test_offline_the_authored_words_stand() -> None:
    pending = lived()
    asyncio.run(voice_pending(pending, 0, AT, StandInGateway(), mood="Low"))
    assert pending[1].payload["text"] == ORIGINAL


def test_only_the_newest_few_each_hour() -> None:
    pending = []
    for n in range(8):
        pending += lived()
    gateway = Scripted("Rowan's off to Leeds, a job they couldn't turn down. I'm gutted, honestly.")
    asyncio.run(voice_pending(pending, 0, AT, gateway, mood="Low"))
    assert gateway.calls == 4
