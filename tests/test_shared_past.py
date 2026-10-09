"""Nobody here shares a past with him from before January, and he remembers who said what."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.recurring_dialogue import _topic_words
from eidos.application.shared_past import invents_shared_past
from eidos.ports.model_gateway import ModelRequest, ModelResponse


def test_lines_inventing_a_past_with_him_are_caught() -> None:
    for invented in (
        "Patrick, I was thinking about that old project we never finished.",
        "I'm sorry it fell through back then.",
        "We used to talk about this years ago, didn't we?",
        "Remember when we fixed that radio together?",
    ):
        assert invents_shared_past(invented), invented
    for fine in (
        "Years ago I let a friendship fade by waiting too long.",
        "I was thinking about that clock you fixed last week.",
        "We should get a coffee sometime.",
        "Back then I lived by the sea.",
    ):
        assert not invents_shared_past(fine), fine


def test_their_own_past_is_framed_as_theirs() -> None:
    words = _topic_words("personal-history-old-regret", "Ellis")
    assert "Ellis's own old regret" in words and "not something the two of them share" in words
    assert _topic_words("weather-today", "Ellis") == "weather today"


class Remembering(StandInGateway):
    """First says something with a made-up past, then, asked again, doesn't."""

    def __init__(self) -> None:
        self.asked: list[dict] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if request.capability == "firmament":
            context = json.loads(request.messages[-1].content)
            self.asked.append(context)
            text = (
                "Ellis here. Mind the step, the floor's still wet."
                if context.get("revision_instruction")
                else "That old project we never finished, Patrick. Still bothers me."
            )
            return ModelResponse(json.dumps({"text": text}), "test", "test", "stop")
        return await super().generate(request)


def test_a_line_with_an_invented_past_is_asked_for_again() -> None:
    from eidos.application.shared_past import REVISION

    gateway = Remembering()
    from eidos.application.cognition import perform

    asked = {"scene_mode": True, "scene_speaker": "ellis", "scene_audience": "pathos"}
    out: list = []
    first = asyncio.run(
        perform(
            gateway, "firmament", asked, datetime(2026, 8, 28, tzinfo=timezone.utc).isoformat(), out
        )
    )
    assert first and invents_shared_past(first)
    second = asyncio.run(
        perform(gateway, "firmament", {**asked, "revision_instruction": REVISION},
                datetime(2026, 8, 28, tzinfo=timezone.utc).isoformat(), out)
    )  # fmt: skip
    assert second and not invents_shared_past(second)


def test_an_earlier_conversation_they_never_had_is_caught() -> None:
    from eidos.application.shared_past import invents_past_talk

    made_up = "I wanted to check if you needed help with that project you mentioned last week."
    assert invents_past_talk(made_up, [])
    assert invents_past_talk("She mentioned something about it the last time we chatted.", [])
    # Something they do remember can be brought up.
    remembered = ["yesterday, in conversation: Patrick said: “The mantel clock project is a pig.”"]
    assert not invents_past_talk("How's that clock project you mentioned?", remembered)
    assert not invents_past_talk("Lovely morning for it.", [])


def test_they_remember_what_he_said_to_them() -> None:
    from eidos.application.gossip import they_remember
    from eidos.domain.events import DomainEvent

    at = datetime(2026, 8, 29, 10, tzinfo=timezone.utc)
    said = DomainEvent(
        "memory.recorded",
        "pathos",
        {"owner": "mara", "category": "scene", "person_id": "pathos",
         "text": "Patrick said: “I'm going freelance.”",
         "simulated_at": (at - timedelta(days=1)).isoformat()},
    )  # fmt: skip
    assert they_remember([said], "mara", at) == [
        "yesterday, in conversation: Patrick said: “I'm going freelance.”"
    ]
    assert they_remember([said], "ellis", at) == []
