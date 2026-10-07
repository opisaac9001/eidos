"""A friend's private trouble is theirs to tell: he doesn't bring it up in the group chat."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.group_chat import MESSAGE, group_chat_events, his_to_share
from eidos.domain.events import DomainEvent
from eidos.ports.model_gateway import ModelRequest, ModelResponse

EVENING = datetime(2026, 8, 26, 19, 0, tzinfo=timezone.utc)
MEMBERS = {"ellis": "Ellis Shaw", "rowan": "Rowan Hale", "mara": "Mara Quinn"}


def concern(concern_id, text, person_id=None):
    return DomainEvent(
        "concern.opened",
        "pathos",
        {
            "concern_id": concern_id,
            "text": text,
            **({"person_id": person_id} if person_id else {}),
            "simulated_at": (EVENING - timedelta(hours=3)).isoformat(),
        },
    )


def chat(speaker, text, news=False, minutes=10):
    return DomainEvent(
        MESSAGE,
        "pathos",
        {
            "chat_id": "the-lot",
            "speaker_id": speaker,
            "speaker_name": MEMBERS.get(speaker, "Patrick").split()[0],
            "text": text,
            "news": news,
            "simulated_at": (EVENING - timedelta(minutes=minutes)).isoformat(),
        },
    )


WORRY = concern("c1", "Rowan's mum isn't well; they're up and down the motorway.", "rowan")
OWN = concern("c2", "The rent's going up in October.")


def test_his_own_worries_are_his_to_share_a_friends_are_not() -> None:
    assert his_to_share([WORRY, OWN], MEMBERS) == ["The rent's going up in October."]
    # Named without a person id, still not his to tell.
    named = concern("c3", "Mara's been struggling since the break-up.")
    assert his_to_share([named, OWN], MEMBERS) == ["The rent's going up in October."]


def test_once_theyve_told_the_group_he_can_mention_it() -> None:
    told = chat("rowan", "Mum's back in hospital, so I'm going down again", news=True)
    assert WORRY.payload["text"] in his_to_share([WORRY, told], MEMBERS)


class Blabs(StandInGateway):
    def __init__(self, line: str) -> None:
        self.line = line
        self.asked: list[dict] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if request.capability == "pathos_text":
            self.asked.append(json.loads(request.messages[-1].content))
            return ModelResponse(json.dumps({"text": self.line}), "test", "test", "stop")
        if request.capability == "firmament":
            return ModelResponse(json.dumps({"text": "anyone about?"}), "test", "test", "stop")
        return await super().generate(request)


def _his_posts(history, line):
    gateway = Blabs(line)
    out = []
    for minutes in range(0, 600, 60):
        out += asyncio.run(
            group_chat_events(
                [*history, *out], EVENING + timedelta(minutes=minutes), gateway,
                members=MEMBERS, free_to_look=True,
                on_his_mind=his_to_share([*history, *out], MEMBERS),
            )
        )  # fmt: skip
    return gateway, [e for e in out if e.kind == MESSAGE and e.payload["speaker_id"] == "pathos"]


def _evening():
    # Fresh messages each time: whether he replies is his own roll on each one.
    return [WORRY, chat("mara", "how's everyone doing?"), chat("ellis", "knackered", minutes=5)]


def test_a_post_giving_away_a_friends_trouble_isnt_sent() -> None:
    tried = 0
    for _ in range(30):
        gateway, posts = _his_posts(_evening(), "thinking of Rowan, hope your mum's on the mend")
        assert posts == []
        if gateway.asked:
            tried += 1
            assert all("isn't well" not in json.dumps(a) for a in gateway.asked)
            assert "privately is theirs to share" in gateway.asked[0]["permission"]
    assert tried, "he did read and try to reply"


def test_an_ordinary_post_still_goes() -> None:
    assert any(_his_posts(_evening(), "not bad, long day at the bench")[1] for _ in range(30))
