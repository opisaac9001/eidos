"""His voice can draw on his own account of his life before Alderwick, the parts that bear
on the moment, as background rather than memories."""

import json

from eidos.adapters.http_gateway import ROLE_FIELDS
from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.domain.life_story import INTERVIEW, passages_for
from eidos.domain.persona import PERSONA_DIRECTIVE


def test_the_story_fits_his_authored_background() -> None:
    told = " ".join(answer for _, answer in INTERVIEW)
    for fact in ("Wye", "Helen", "Richard", "Tom", "Jess", "Isla", "Gulliver", "Bristol", "Ellis"):
        assert fact in told
    # What his profile says not to import stays out.
    for dropped in ("Volvo", "freelance"):
        assert dropped not in told


def test_only_the_parts_that_bear_on_the_moment() -> None:
    assert passages_for("Did you have a dog growing up?")[0]["asked"] == "Did you have pets?"
    assert passages_for("How did you end up at Ellis's workshop?")[0]["asked"] == (
        "How did you end up at the workshop?"
    )
    assert passages_for("Hiya") == []
    assert len(passages_for("tell me about your family, your mum and dad and brother")) <= 2


def test_his_voice_gets_the_passage_and_the_rule(tmp_path) -> None:
    class Capturing(StandInGateway):
        def __init__(self) -> None:
            self.requests = []

        async def generate(self, request):
            self.requests.append(request)
            return await super().generate(request)

    gateway = Capturing()
    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), gateway)
    life.advance(10)
    life.request_visit("visit")
    life.chat("Where did you grow up, anyway?", "turn")
    request = next(r for r in reversed(gateway.requests) if r.capability == "pathos")
    context = json.loads(request.messages[0].content)
    assert context["my_life_story"][0]["asked"] == "Where did you grow up?"
    assert "my_life_story" in ROLE_FIELDS["pathos"]
    assert "my_life_story" in PERSONA_DIRECTIVE
    # Background, not memory: nothing from it is recorded as something he lived.
    assert not any(
        e.kind == "memory.recorded" and "crown cut into the chalk" in str(e.payload.get("text"))
        for e in life.history()
    )
