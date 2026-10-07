"""Plans made in the group chat become real invitations he decides on, and he answers them."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.group_chat import MESSAGE, PLAN_PREFIX, group_chat_events
from eidos.domain.events import DomainEvent
from eidos.ports.model_gateway import ModelRequest, ModelResponse

MORNING = datetime(2026, 8, 24, 9, 0, tzinfo=timezone.utc)
MEMBERS = {"ellis": "Ellis", "rowan": "Rowan", "mara": "Mara"}
PLACES = frozenset({"cinema", "music-room", "riverside", "market-hall", "cafe", "home"})


class Friends(StandInGateway):
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if request.capability == "firmament":
            context = json.loads(request.messages[-1].content)
            said = f"who's up for it? ({context['scene_speaker']})"
            return ModelResponse(json.dumps({"text": said}), "test", "test", "stop")
        if request.capability == "pathos_text":
            return ModelResponse(json.dumps({"text": "count me in"}), "test", "test", "stop")
        return await super().generate(request)


def run(history, at, gateway=None, free=True):
    return asyncio.run(
        group_chat_events(
            history, at, gateway or Friends(), members=MEMBERS, free_to_look=free, places=PLACES
        )
    )


def _fortnight(free=False):
    history: list[DomainEvent] = []
    for day in range(14):
        for hour in range(9, 22):
            history += run(history, MORNING + timedelta(days=day, hours=hour - 9), free=free)
    return history


def test_a_friend_suggests_a_plan_now_and_then_as_a_real_invitation() -> None:
    history = _fortnight()
    made = [e for e in history if e.kind == "invitation.made"]
    assert 1 <= len(made) <= 5  # now and then, not every day
    for invitation in made:
        assert invitation.payload["invitation_id"].startswith(PLAN_PREFIX)
        assert invitation.payload["inviter_id"] in MEMBERS
        assert invitation.payload["location_id"] in PLACES
        said = datetime.fromisoformat(invitation.payload["simulated_at"])
        starts = datetime.fromisoformat(invitation.payload["starts_at"])
        assert timedelta(hours=12) < starts - said < timedelta(days=8)
        opened = next(
            e
            for e in history
            if e.kind == "social.request_opened"
            and e.payload["request_id"] == invitation.payload["request_id"]
        )
        assert opened.payload["responder_id"] == "pathos"
        assert opened.payload["earliest_start"] == invitation.payload["starts_at"]
        post = next(
            e
            for e in history
            if e.kind == MESSAGE
            and e.payload.get("invitation_id") == invitation.payload["invitation_id"]
        )
        assert post.payload["speaker_id"] == invitation.payload["inviter_id"]
    # Never two plans in the air at once.
    times = sorted(datetime.fromisoformat(e.payload["simulated_at"]) for e in made)
    assert all(b - a >= timedelta(days=4) for a, b in zip(times, times[1:]))


def test_no_places_no_plans() -> None:
    history: list[DomainEvent] = []
    for hour in range(60):
        history += asyncio.run(
            group_chat_events(
                history, MORNING + timedelta(hours=hour), Friends(), members=MEMBERS,
                free_to_look=False,
            )
        )  # fmt: skip
    assert not any(e.kind == "invitation.made" for e in history)


def _decided(kind: str) -> list[DomainEvent]:
    invitation_id = f"{PLAN_PREFIX}rowan-2026-08-24"
    return [
        DomainEvent(
            MESSAGE,
            "pathos",
            {
                "chat_id": "the-lot",
                "speaker_id": "rowan",
                "text": "film at the Regent on Thursday?",
                "news": False,
                "invitation_id": invitation_id,
                "simulated_at": MORNING.isoformat(),
            },
        ),
        DomainEvent(
            kind,
            "pathos",
            {
                "invitation_id": invitation_id,
                "request_id": f"request-{invitation_id}",
                "person_id": "rowan",
                "simulated_at": (MORNING + timedelta(hours=2)).isoformat(),
            },
        ),
    ]


def test_he_answers_a_plan_once_he_has_decided_and_only_once() -> None:
    for kind, cue in (("invitation.accepted", "said yes"), ("invitation.declined", "can't make")):
        history = _decided(kind)
        gateway = Friends()
        at = MORNING + timedelta(hours=3)
        out = run(history, at, gateway)
        answers = [e for e in out if e.kind == MESSAGE and e.payload.get("answers")]
        assert len(answers) == 1 and answers[0].payload["speaker_id"] == "pathos"
        asked = next(r for r in gateway.requests if r.capability == "pathos_text")
        assert cue in asked.messages[-1].content
        later = run([*history, *out], at + timedelta(hours=1))
        assert not any(e.payload.get("answers") for e in later if e.kind == MESSAGE)


def test_he_does_not_answer_while_he_cannot_look() -> None:
    out = run(_decided("invitation.accepted"), MORNING + timedelta(hours=3), free=False)
    assert not any(e.payload.get("answers") for e in out if e.kind == MESSAGE)


def test_a_plan_he_says_yes_to_is_booked_like_any_invitation() -> None:
    from eidos.application.inbound_invitations import pathos_invitation_response_events
    from eidos.domain.planning import PlanningState
    from eidos.domain.world_catalog import project_world_catalog

    catalog = project_world_catalog([])
    history: list[DomainEvent] = []
    at = MORNING
    while not any(e.kind == "invitation.made" for e in history):
        history += asyncio.run(
            group_chat_events(
                history, at, Friends(), members=MEMBERS, free_to_look=False,
                places=frozenset(catalog.places),
            )
        )  # fmt: skip
        at += timedelta(hours=1)
        assert at < MORNING + timedelta(days=60)
    later = at + timedelta(hours=5)
    out = pathos_invitation_response_events(
        history,
        later,
        len(history),
        pathos_awake=True,
        pathos_available=True,
        energy=0.85,
        rest=0.85,
        mastery=0.7,
        values={"care": 0.8, "curiosity": 0.8},
        affect_valence=0.2,
        affect_arousal=0.3,
        sustained_low_hours=0,
        planning=PlanningState(),
        catalog=catalog,
    )
    kinds = [e.kind for e in out]
    assert "invitation.accepted" in kinds or "invitation.declined" in kinds
    if "invitation.accepted" in kinds:
        assert "schedule.created" in kinds
