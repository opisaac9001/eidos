"""A phone call has words in it, both ways."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.phone_talk import TURN, call_talk_events
from eidos.domain.events import DomainEvent
from eidos.ports.model_gateway import ModelRequest, ModelResponse

AT = datetime(2026, 9, 11, 10, 7, tzinfo=timezone.utc)
NAMES = {"rowan": "Rowan", "mara": "Mara Bell"}


class OnThePhone(StandInGateway):
    def __init__(self) -> None:
        self.asked: list[dict] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        context = json.loads(request.messages[-1].content)
        self.asked.append(context)
        if request.capability == "firmament":
            who = context["scene_speaker"]
            said = f"Just ringing to see how you are, it's been a while. ({who})"
            return ModelResponse(json.dumps({"text": said}), "test", "test", "stop")
        if request.capability == "pathos_text":
            return ModelResponse(
                json.dumps({"text": "Not bad, cheers. Busy with the docs. How's your mum?"}),
                "test", "test", "stop",
            )  # fmt: skip
        return await super().generate(request)


def talk(history, gateway):
    return asyncio.run(call_talk_events(history, AT, gateway, names=NAMES))


def test_a_call_he_answers_has_their_opening_his_reply_and_their_sign_off() -> None:
    answered = DomainEvent(
        "phone.call_answered",
        "pathos",
        {"call_id": "rowan-call-1", "caller_id": "rowan", "scene_id": None,
         "simulated_at": (AT - timedelta(minutes=5)).isoformat()},
    )  # fmt: skip
    gateway = OnThePhone()
    out = talk([answered], gateway)
    turns = [(e.payload["speaker"], e.payload["text"]) for e in out if e.kind == TURN]
    assert [s for s, _ in turns] == ["Rowan", "Patrick", "Rowan"]
    memories = [e.payload["text"] for e in out if e.kind == "memory.recorded"]
    assert memories[0].startswith("Rowan rang: “") and memories[1].startswith(
        "On the phone to Rowan, I said"
    )
    assert memories[2].startswith("Rowan, before ringing off")
    # His reply was asked with the call so far in front of him.
    his = next(c for c in gateway.asked if c.get("task") == "call")
    assert his["on_the_phone_so_far"][0].startswith("Rowan: Just ringing")
    # Once talked, not again; and a call two hours old is left alone.
    assert talk([answered, *out], gateway) == []
    old = DomainEvent("phone.call_answered", "pathos", {**answered.payload, "call_id": "old",
                      "simulated_at": (AT - timedelta(hours=3)).isoformat()})  # fmt: skip
    assert talk([old], gateway) == []


def test_a_call_he_made_goes_on_past_their_first_answer() -> None:
    sent = DomainEvent(
        "contact.reached_out",
        "pathos",
        {"contact_id": "c1", "person_id": "rowan", "person_name": "Rowan", "channel": "call",
         "text": "You alright after all that motorway running?", "reply_due_at": AT.isoformat(),
         "simulated_at": AT.isoformat()},
    )  # fmt: skip
    answer = DomainEvent(
        "contact.reply_received",
        "pathos",
        {"contact_id": "c1", "person_id": "rowan", "person_name": "Rowan",
         "text": "Yeah, up and down a lot. How are you?", "simulated_at": AT.isoformat()},
    )  # fmt: skip
    out = talk([sent, answer], OnThePhone())
    turns = [(e.payload["speaker"], e.payload["text"]) for e in out if e.kind == TURN]
    assert [s for s, _ in turns] == ["Patrick", "Rowan"]
    assert turns[0][1].startswith("Not bad, cheers.")
    # A text, answered, isn't a call to carry on.
    texted = DomainEvent("contact.reached_out", "pathos", {**sent.payload, "channel": "text"})
    assert talk([texted, answer], OnThePhone()) == []
