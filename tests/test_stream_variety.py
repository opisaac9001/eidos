"""The stream learns from thoughts it had turned away, and notices a rut in other words."""

import json

from eidos.adapters.http_gateway import compact_context
from eidos.adapters.sqlite_inner_stream import SQLiteInnerStream
from eidos.application.inner_stream import InnerStream, worn_out
from eidos.ports.model_gateway import ModelGateway, ModelRequest, ModelResponse


def test_the_same_rut_in_different_words_is_still_a_rut() -> None:
    recent = [
        "Ellis's hammer again. Can't hear myself think.",
        "That drill of his is going to drive me mad.",
        "Bench needs sanding before lunch.",
    ]
    tired = worn_out(recent, {"Ellis"})
    assert {"noise", "hammer", "drill"} <= set(tired)
    assert "ellis" not in tired


def test_a_thought_turned_away_is_named_so_the_next_try_differs(tmp_path) -> None:
    class Looping(ModelGateway):
        model = "tiny"

        def __init__(self) -> None:
            self.contexts: list[dict] = []
            self.lines = iter(
                [
                    "Workshop's quiet this morning, just the radio.",
                    "Workshop's quiet this morning, just the radio.",
                    "Need to order more brass screws.",
                ]
            )

        async def generate(self, request: ModelRequest) -> ModelResponse:
            self.contexts.append(json.loads(request.messages[-1].content))
            return ModelResponse(json.dumps({"text": next(self.lines)}), "tiny", "t", "stop")

    world = {
        "time": "2026-08-26T10:20:00+00:00",
        "pathos": {"location": "The workshop", "location_id": "workshop", "awake": True},
        "people": [],
    }
    gateway = Looping()
    stream = InnerStream(
        SQLiteInnerStream(tmp_path / "world.sqlite3"), gateway, lambda: (world, True)
    )
    stream.step()
    stream.step()  # the same thought again: turned away
    assert stream.rejected
    stream.step()
    told = gateway.contexts[-1]
    assert told["not_again"] == ["Workshop's quiet this morning, just the radio."]
    compact = compact_context("murmur", told)
    assert compact["already_tried_say_something_else"] == told["not_again"]
