"""His passing thoughts stay true to his life: who's where, what happened, when it is."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from eidos.adapters.http_gateway import compact_context, time_of_year
from eidos.adapters.sqlite_inner_stream import SQLiteInnerStream
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.inner_stream import (
    Cue,
    InnerStream,
    cues,
    grounding,
    invented_happening,
    placed_with_him,
    stream_context,
)
from eidos.application.reaching_out import REACHED, reach_out_events, reply_events
from eidos.ports.model_gateway import ModelGateway, ModelRequest, ModelResponse

NAMES = {"Rowan", "Ellis", "Mara", "Beth", "Pritchard", "Tom", "Gulliver"}


def home_alone() -> dict:
    return {
        "time": "2026-08-25T19:20:00+00:00",
        "pathos": {"location": "Home", "location_id": "home", "awake": True},
        "people": [
            {
                "id": "rowan",
                "name": "Rowan",
                "location_id": "park",
                "occupation": "Illustrator",
                "familiarity": 0.8,
            },
            {
                "id": "ellis",
                "name": "Ellis",
                "location_id": "workshop",
                "occupation": "Repair artist",
                "familiarity": 0.8,
            },
        ],
        "memories": [
            {"text": "I texted Rowan: “Morning, how's your mum?”", "owner": "pathos"},
            {"text": "Ellis hands Pathos the hinge and mentions the bench.", "owner": "pathos"},
        ],
        "selfhood": {
            "whats_going_on_with_his_friends": [
                {"who": "Rowan", "what": "Rowan told me their mum's not been well."}
            ],
            "family": [
                {"who": "Mum (Helen Shaw)", "relation": "mother", "about": "Gardens."},
                {"who": "Dad (Richard Shaw)", "relation": "father", "about": "Restores clocks."},
            ],
            "reading_watching_listening": {
                "currently": [{"kind": "album", "title": "Young Team", "by": "Mogwai"}]
            },
        },
        "goals": [
            {"title": "Make a small atlas of neighbourhood sounds", "status": "active"},
            {"title": "Spend time with Townsfolk 8103", "status": "active"},
        ],
    }


def test_a_thought_cant_report_a_call_text_or_visit_that_never_happened() -> None:
    known = grounding(home_alone())
    for invented in (
        "Rowan called about their mum, felt bad.",
        "Wonder why Rowan texts about The Bear.",
        "Rowan dropped by. Thought he'd bring sweets, but he didn't.",
    ):
        assert invented_happening(invented, NAMES, known) is not None, invented
    for fine in (
        "Rowan told me their mum's ill. Poor them.",
        "Rowan hasn't texted back yet.",
        "Hope Rowan calls tonight.",
        "Should text Rowan later.",
        "Ellis mentioned the bench again.",
    ):
        assert invented_happening(fine, NAMES, known) is None, fine
    # Someone in the room with him can say things.
    assert invented_happening("Ellis said the kettle's on.", NAMES, [], ["Ellis"]) is None


def test_alone_at_home_nobody_is_in_the_room_with_him() -> None:
    alone = {"alone": True}
    for present in (
        "Rowan's finally asleep.",
        "Hope Rowan doesn't hear me now.",
        "Hope Rowan hasn't noticed me working late.",
        "Rowan looks so still today.",
        "Rowan's sketchbook is open on the table.",
    ):
        assert placed_with_him(present, alone, NAMES) == "Rowan", present
    for elsewhere in (
        "Wonder if Rowan's asleep yet.",
        "Rowan looks after their mum so much.",
        "Rowan's mum sounds awful.",
        "Ellis must be sleeping in.",
    ):
        assert placed_with_him(elsewhere, alone, NAMES) is None, elsewhere
    assert placed_with_him("Rowan's finally asleep.", {"with_him": ["Rowan"]}, NAMES) is None


def test_he_knows_who_people_are_where_his_family_live_and_that_gulliver_is_gone() -> None:
    context = stream_context(
        home_alone(),
        ["Rowan's mum sounds awful.", "Dad's clocks, Mum's garden."],
        Cue("wander", "Gulliver, the old family dog, who died years ago"),
    )
    who = context["who_is_who"]
    assert who["Rowan"] == "illustrator; they/them"
    assert "alive and well, at home in Wye" in who["Mum"]
    assert "alive and well, at home in Wye" in who["Dad"]
    assert "died years ago" in who["Gulliver"]
    # "Rowan's mum" alone isn't his own mum.
    only_rowans = stream_context(home_alone(), ["Rowan's mum sounds awful."], None)
    assert "Mum" not in only_rowans["who_is_who"]


def test_titles_and_goals_are_said_for_what_they_are() -> None:
    texts = [cue.text for cue in cues(home_alone()) if cue.kind == "wanting"]
    assert "Young Team (Mogwai), the album he's listening to" in texts
    assert "something he means to do: Make a small atlas of neighbourhood sounds" in texts
    assert not any("Townsfolk" in text for text in texts)


def test_a_small_model_knows_the_date_and_season_in_words() -> None:
    assert time_of_year("2026-08-25T21:21:00+00:00") == "Tuesday 25 August, late summer"
    assert time_of_year("2026-12-03T09:00:00+00:00") == "Thursday 3 December, early winter"
    details = compact_context("murmur", {"time": "2026-08-25T21:21:00+00:00"})
    assert details["time_of_year"] == "Tuesday 25 August, late summer"


def test_the_stream_turns_away_a_made_up_visit(tmp_path) -> None:
    class Confabulating(ModelGateway):
        model = "tiny"

        def __init__(self) -> None:
            self.lines = iter(["Rowan dropped by earlier with sweets.", "Quiet night, this."])

        async def generate(self, request: ModelRequest) -> ModelResponse:
            return ModelResponse(json.dumps({"text": next(self.lines)}), "tiny", "test", "stop")

    world = home_alone()
    stream = InnerStream(
        SQLiteInnerStream(tmp_path / "world.sqlite3"), Confabulating(), lambda: (world, True)
    )
    stream._tried.append("Rowan's mum")  # Rowan is on his mind, so naming them is fine
    stream.step()
    assert stream.rejected and "made up" in str(stream.last_error)
    stream.step()
    assert [thought.text for thought in stream.store.recent(5)] == ["Quiet night, this."]


class Capturing(StandInGateway):
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        return await super().generate(request)


def _sent(gateway: ModelGateway, at: datetime) -> list:
    while True:
        sent = asyncio.run(
            reach_out_events(
                [],
                at,
                gateway,
                person_id="ellis",
                person_name="Ellis",
                who_they_are="repair artist",
                on_his_mind=["Ellis seemed tired."],
                mood="quiet",
            )
        )
        if next(e for e in sent if e.kind == REACHED).payload["reply_due_at"]:
            return sent


def test_a_reply_fits_where_they_are_and_comes_in_person_if_theyre_with_him() -> None:
    at = datetime(2026, 8, 25, 8, 20, tzinfo=timezone.utc)
    gateway = Capturing()
    sent = _sent(gateway, at)
    here = {
        "where_they_are": "at the workshop",
        "what_they_are_doing": "work",
        "with_patrick": True,
    }
    replies = asyncio.run(
        reply_events(sent, at + timedelta(hours=3), gateway, lambda person_id: here)
    )
    request = next(r for r in gateway.requests if r.capability == "firmament")
    context = json.loads(request.messages[-1].content)
    assert context["personal_relationship_context"]["right_now"] == here
    assert context["location"] == "in person, at the workshop"
    assert "don't offer to come round" in context["personal_relationship_context"]["instruction"]
    memory = next(e for e in replies if e.kind == "memory.recorded")
    assert memory.payload["text"].startswith("Ellis answered my text in person")


def test_he_only_knows_what_he_could_know() -> None:
    from eidos.application.inner_stream import cues

    world = home_alone()
    # Someone he's only heard of: their name, not what they do.
    world["people"] = [
        {"id": "townsfolk-9", "name": "June Hollis", "location_id": "market-hall",
         "occupation": "Market trader", "familiarity": 0.05},
    ]  # fmt: skip
    context = stream_context(world, ["June Hollis, apparently."], Cue("wander", "June Hollis"))
    assert "trader" not in str(context.get("who_is_who", {})).casefold()
    # A dead phone shows him nothing from the group chat.
    world["phone"] = {
        "recent": [{"from": "Rowan", "text": "pub later?"}],
        "unread": 1,
        "dead": True,
    }
    assert not [cue for cue in cues(world) if cue.kind == "phone"]
    world["phone"]["dead"] = False
    assert [cue for cue in cues(world) if cue.kind == "phone"]


def test_at_his_parents_they_are_with_him() -> None:
    world = home_alone()
    world["pathos"] = {
        **world["pathos"],
        "location_id": "wye-home",
        "location": "Mum and Dad's, Wye",
    }
    context = stream_context(world, ["Mum's roast."], Cue("here", "Mum and Dad's, Wye"))
    assert {"Mum", "Dad"} <= set(context["with_him"]) and not context.get("alone")
    assert placed_with_him("Mum's in the kitchen humming.", context, NAMES) is None
    from eidos.application.inner_stream import somewhere_else

    assert somewhere_else("Sitting here in Wye tonight.", "Mum and Dad's, Wye") is None
