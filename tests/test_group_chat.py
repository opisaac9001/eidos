"""His friends' group chat goes on without him; he reads it when he's free and sometimes
says something."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.group_chat import MESSAGE, READ, group_chat_events, phone_view, unread
from eidos.application.inner_stream import cues
from eidos.domain.events import DomainEvent
from eidos.ports.model_gateway import ModelRequest, ModelResponse

EVENING = datetime(2026, 8, 26, 19, 0, tzinfo=timezone.utc)
MEMBERS = {"ellis": "Ellis", "rowan": "Rowan", "mara": "Mara"}


class Friends(StandInGateway):
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if request.capability == "firmament":
            context = json.loads(request.messages[-1].content)
            said = f"anyone about later? ({context['scene_speaker']})"
            return ModelResponse(json.dumps({"text": said}), "test", "test", "stop")
        return await super().generate(request)


def evening(history, at, free=True, gateway=None):
    return asyncio.run(
        group_chat_events(history, at, gateway or Friends(), members=MEMBERS, free_to_look=free)
    )


def test_the_chat_goes_on_busier_in_the_evening_and_he_reads_when_free() -> None:
    history: list[DomainEvent] = []
    for day in range(6):
        for hour in range(8, 24):
            at = EVENING.replace(hour=hour) + timedelta(days=day)
            history += evening(history, at, free=not 10 <= hour < 16)
    posts = [e for e in history if e.kind == MESSAGE]
    friends = [e for e in posts if e.payload["speaker_id"] != "pathos"]
    evenings = [e for e in friends if datetime.fromisoformat(e.payload["simulated_at"]).hour >= 18]
    days = [e for e in friends if datetime.fromisoformat(e.payload["simulated_at"]).hour < 18]
    assert friends and len(evenings) / 6 > len(days) / 10  # per hour, evenings are busier
    reads = [e for e in history if e.kind == READ]
    assert reads and all(
        not 10 <= datetime.fromisoformat(e.payload["simulated_at"]).hour < 16 for e in reads
    )
    mine = [e for e in posts if e.payload["speaker_id"] == "pathos"]
    assert mine and len(mine) < len(friends)  # he chimes in, but doesn't talk the most
    per_day: dict[str, int] = {}
    for post in mine:
        day = post.payload["simulated_at"][:10]
        per_day[day] = per_day.get(day, 0) + 1
    assert max(per_day.values()) <= 4
    assert any(e.kind == "memory.recorded" for e in history)


def test_a_friends_news_goes_to_the_group() -> None:
    news = DomainEvent(
        "friend.life_event",
        "pathos",
        {
            "person_id": "rowan",
            "kind": "engaged",
            "text": "Rowan's engaged!",
            "simulated_at": (EVENING - timedelta(minutes=20)).isoformat(),
        },
    )
    gateway = Friends()
    out = evening([news], EVENING, gateway=gateway)
    posted = next(e for e in out if e.kind == MESSAGE)
    assert posted.payload["speaker_id"] == "rowan" and posted.payload["news"]
    topic = json.loads(gateway.requests[0].messages[-1].content)["scene_topic"]
    assert "Rowan's engaged!" in topic


def test_an_unread_message_buzzes_into_his_thoughts() -> None:
    out: list[DomainEvent] = []
    for day in range(3):
        for hour in range(18, 23):
            out += evening(out, EVENING.replace(hour=hour) + timedelta(days=day), free=False)
    history = [e for e in out if e.kind == MESSAGE]
    assert unread(history)
    snapshot = {
        "time": EVENING.isoformat(),
        "pathos": {"location_id": "home", "awake": True},
        "people": [],
        "phone": phone_view(history),
    }
    phone = [cue for cue in cues(snapshot) if cue.kind == "phone"]
    assert phone and phone[0].weight > 1 and "in the group chat" in phone[0].text
