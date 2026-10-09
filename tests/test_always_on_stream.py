"""His inner monologue keeps running between the quarter-hour pulses."""

import json
import random
from datetime import datetime, timedelta

import pytest

from eidos.adapters.model_settings import SettingsError, validate
from eidos.adapters.sqlite_inner_stream import SQLiteInnerStream
from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.adapters.web_server import Runtime
from eidos.application.inner_stream import (
    STAND_IN_GAP_SECONDS,
    Cue,
    InnerStream,
    StreamSettings,
    StreamThought,
    choose_cue,
    cues,
    near_repeat,
    pick_for_pulse,
    stream_context,
)
from eidos.application.life import Life
from eidos.ports.model_gateway import ModelGateway, ModelRequest, ModelResponse


def snapshot(awake: bool = True) -> dict:
    return {
        "time": "2026-03-02T10:20:00+00:00",
        "weather": "Light rain",
        "pathos": {
            "location": "The workshop",
            "location_id": "workshop",
            "awake": awake,
            "energy": 0.3,
            "needs": {"hunger": 0.7},
            "surroundings": {"activity": "Radio on, a lamp on the bench"},
        },
        "emotion": {"label": "content", "secondary_label": "restless", "intensity": 0.4},
        "time_budget": {
            "next_plan": "Tea with Mara",
            "minutes_until_start": 40,
            "free_minutes": 25,
        },
        "activity_execution": [{"title": "Rewire the brass lamp", "is_working": True}],
        "people": [
            {"name": "Ellis", "location_id": "workshop"},
            {"name": "Mara", "location_id": "cafe"},
        ],
        "memories": [{"recalled_text": "Mum rang on Sunday about the garden.", "source": "lived"}],
        "selfhood": {"family": [{"who": "Dad", "owes_them_a_call": True}]},
        "feed": [
            {"text": "Heard that the council budget vote was delayed.", "source": "real-news"}
        ],
        "finances": {"balance_pence": 42_000},
        "mind": {"layers": [{"layer": "attention", "focus_text": "the lamp's wiring"}]},
        "config": {"running": True},
    }


class Thinker(ModelGateway):
    """A real-model stand-in that says something new every time."""

    model = "tiny-thinker"

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.lines = iter(
            [
                "This wiring's older than the radio. Someone soldered it with love.",
                "Tea with Mara soon. Should wash my hands first, they're black.",
                "Dad. I really do need to ring him back tonight.",
                "Hungry now, properly. The biscuit tin at the back is probably empty.",
            ]
        )

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(json.loads(request.messages[-1].content))
        return ModelResponse(json.dumps({"text": next(self.lines)}), "tiny-thinker", "test", "stop")


def test_his_mind_can_drift_to_everything_around_and_inside_him() -> None:
    kinds = {cue.kind for cue in cues(snapshot())}
    assert {"here", "doing", "next", "body", "feeling", "person", "memory"} <= kinds
    assert {"someone", "news", "money"} <= kinds
    texts = [cue.text for cue in cues(snapshot())]
    assert "Ellis is here" in texts and not any("Mara is here" in text for text in texts)


def test_the_stream_doesnt_drift_to_the_same_kind_of_thing_twice_running() -> None:
    rng = random.Random(4)
    # Drifting away goes somewhere new each time...
    available = [Cue("memory", "the old flat"), Cue("concern", "Rowan's mum")]
    assert all(choose_cue(available, ["memory"], rng).kind == "concern" for _ in range(20))
    # ...but a mind can stay on the moment it's in.
    here = [Cue("here", "the workshop"), Cue("memory", "the old flat")]
    assert any(choose_cue(here, ["here"], rng).kind == "here" for _ in range(20))
    assert choose_cue([], ["here"], rng) is None


def test_each_thought_follows_on_from_the_last_few(tmp_path) -> None:
    store = SQLiteInnerStream(tmp_path / "world.sqlite3")
    gateway = Thinker()
    stream = InnerStream(store, gateway, lambda: (snapshot(), True), rng=random.Random(1))
    assert stream.step() == 20
    assert stream.step() == 20
    first, second = gateway.requests
    assert first["recent_inner_stream"] == []
    assert second["recent_inner_stream"] == [store.recent(2)[1].text]
    assert second["drifting_to"] and second["location"] == "The workshop"
    assert [thought.model for thought in store.recent(5)] == ["tiny-thinker"] * 2
    page = stream.view_for_page()
    assert page["state"] == "resting" and len(page["thoughts"]) == 2


def test_the_stream_rests_while_he_sleeps_or_the_world_is_paused(tmp_path) -> None:
    store = SQLiteInnerStream(tmp_path / "world.sqlite3")
    gateway = Thinker()
    asleep = InnerStream(store, gateway, lambda: (snapshot(awake=False), True))
    paused = InnerStream(store, gateway, lambda: (snapshot(), False))
    off = InnerStream(
        store, gateway, lambda: (snapshot(), True), settings=lambda: StreamSettings(False)
    )
    for stream, state in ((asleep, "asleep"), (paused, "paused"), (off, "off")):
        stream.step()
        assert stream.state == state
    assert gateway.requests == [] and store.count() == 0


def test_the_written_stand_ins_run_slowly(tmp_path) -> None:
    stream = InnerStream(
        SQLiteInnerStream(tmp_path / "world.sqlite3"),
        StandInGateway(),
        lambda: (snapshot(), True),
    )
    assert stream.step() == STAND_IN_GAP_SECONDS
    assert stream.store.count() == 1


def test_a_looping_thought_is_not_kept() -> None:
    assert near_repeat(
        "Tea with Mara soon, should wash my hands.", ["tea with mara soon should wash my hands"]
    )
    assert not near_repeat("Dad. Must ring him.", ["Tea with Mara soon, should wash my hands."])
    assert near_repeat(
        "Morning air's quiet. Wonder if Hannah's got a latte for me.",
        ["Morning air's quiet. Might sketch some local noises."],
    )
    assert near_repeat(
        "Beth's new job in Bristol. Still too cold to leave coffee on the table, though.",
        ["Bear's asleep in that tree. Still too cold to leave coffee on the table, though."],
    )


def test_the_quarter_hour_keeps_the_thought_that_mattered_most() -> None:
    def thought(id: int, cue_kind: str, text: str, wall_at: float) -> StreamThought:
        return StreamThought(text, "2026-03-02T10:20:00+00:00", wall_at, cue_kind, "", "m", 1, id)

    chosen = pick_for_pulse(
        [
            thought(1, "here", "Rain on the roof.", 100),
            thought(2, "someone", "Dad. I really do need to ring him back tonight, properly.", 200),
            thought(3, "body", "Hungry.", 300),
        ]
    )
    assert chosen is not None and chosen.id == 2


def test_the_pulse_records_the_streams_thought_instead_of_asking_again(tmp_path) -> None:
    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(7)
    store = SQLiteInnerStream(tmp_path / "world.sqlite3")
    stream = InnerStream(store, Thinker(), lambda: (life.snapshot(), True))
    stream.step()
    assert stream.keep_for_pulse(life.pulse_inner_stream)
    kept = [
        event
        for event in life.history()
        if event.kind == "thought.recorded" and event.payload.get("kept_from_stream")
    ]
    assert len(kept) == 1 and kept[0].payload["text"] == store.recent(1)[0].text
    assert kept[0].payload["model"] == "tiny-thinker"
    assert store.recent(1)[0].promoted
    # The same quarter hour is never pulsed twice, so nothing more is kept.
    stream.step()
    assert not stream.keep_for_pulse(life.pulse_inner_stream)
    assert not store.recent(1)[0].promoted


def test_the_runtime_shows_the_stream_and_the_pulse_uses_it(tmp_path) -> None:
    class Clock:
        now = 300.0

        def __call__(self) -> float:
            return self.now

    clock = Clock()
    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(7)
    runtime = Runtime(life, interval=60, clock=clock)
    runtime.start()
    try:
        runtime.stream = InnerStream(
            SQLiteInnerStream(tmp_path / "world.sqlite3"), Thinker(), runtime.stream_view
        )
        with runtime.mutation():
            life.configure(True, 15, "realtime")
        runtime.snapshot()
        runtime.stream.step()
        assert runtime.snapshot()["inner_stream"]["thoughts"][0]["text"].startswith("This wiring")
        clock.now += 900
        with runtime.mutation():
            pass
        kept = [
            event
            for event in life.history()
            if event.kind == "thought.recorded" and event.payload.get("kept_from_stream")
        ]
        assert [event.payload["text"] for event in kept] == [
            "This wiring's older than the radio. Someone soldered it with love."
        ]
    finally:
        runtime.stream = None
        runtime.close()


def test_stream_settings_are_checked() -> None:
    assert validate({"stream": {"enabled": True, "gap_seconds": 30}}, {})["stream"] == {
        "enabled": True,
        "gap_seconds": 30,
    }
    for bad in ({"gap_seconds": 1}, {"enabled": "yes"}, {"pace": 3}):
        with pytest.raises(SettingsError):
            validate({"stream": bad}, {})


def test_small_models_are_told_where_his_mind_is_wandering() -> None:
    from eidos.adapters.http_gateway import compact_context

    context = stream_context(snapshot(), ["Rain again."], Cue("someone", "owes Dad a call"))
    details = compact_context("murmur", context)
    assert details["mind_wanders_to"] == "owes Dad a call"
    assert details["recent_thoughts"] == ["Rain again."]


def test_a_thought_names_only_people_in_front_of_his_mind() -> None:
    from eidos.application.inner_stream import known_names, stray_name

    names = known_names(snapshot())
    assert {"Ellis", "Mara", "Tom"} <= names
    context = stream_context(snapshot(), ["Tom's kitchen is so small."], Cue("money", "£420"))
    assert stray_name("Tom's money is all I've got.", context, names) == "Tom"
    assert stray_name("Four hundred quid. Rent's soon.", context, names) is None
    # Tea with Mara is his next plan, so she is on his mind.
    assert stray_name("Tea with Mara soon. Hands are filthy.", context, names) is None
    here = stream_context(snapshot(), [], Cue("person", "Ellis is here"))
    assert stray_name("Ellis is humming again.", here, names) is None


def test_small_models_get_the_time_of_day_in_words() -> None:
    from eidos.adapters.http_gateway import compact_context

    details = compact_context("murmur", {"time": "2026-01-08T07:42:00+00:00"})
    assert details["time_of_day"] == "early morning"


def test_the_stream_sees_his_clock_moving_between_commits(tmp_path) -> None:
    class Clock:
        now = 300.0

        def __call__(self) -> float:
            return self.now

    clock = Clock()
    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(7)
    runtime = Runtime(life, interval=60, clock=clock)
    runtime.start()
    try:
        with runtime.mutation():
            life.configure(True, 15, "realtime")
        committed = runtime.cached["time"]
        clock.now += 120
        seen, running = runtime.stream_view()
        assert running
        assert datetime.fromisoformat(seen["time"]) - datetime.fromisoformat(committed) == (
            timedelta(seconds=120)
        )
    finally:
        runtime.close()


def test_his_mind_drifts_to_his_own_memories_not_residents() -> None:
    world = snapshot()
    world["memories"] = [
        {"text": "Hannah Fenwick notices something out of place.", "owner": "hannah-fenwick"},
        {"text": "Mum rang about the garden.", "owner": "pathos"},
    ]
    memories = [cue.text for cue in cues(world) if cue.kind == "memory"]
    assert memories == ["Mum rang about the garden."]


def test_a_rejected_thought_doesnt_slow_the_stream_like_an_outage(tmp_path) -> None:
    class Looping(Thinker):
        async def generate(self, request: ModelRequest) -> ModelResponse:
            return ModelResponse(json.dumps({"text": "Same again, same again."}), "m", "t", "stop")

    stream = InnerStream(
        SQLiteInnerStream(tmp_path / "world.sqlite3"), Looping(), lambda: (snapshot(), True)
    )
    assert stream.step() == 20  # the first is kept
    for _ in range(4):
        assert stream.step() == 20  # repeats are dropped without backing off
    assert stream.failures == 0 and stream.state == "resting"


def test_his_mood_colours_the_stream_only_when_his_mind_turns_to_it() -> None:
    assert "emotion" not in stream_context(snapshot(), [], Cue("here", "The workshop"))
    feeling = stream_context(snapshot(), [], Cue("feeling", "content"))
    assert feeling["emotion"]["label"] == "content"


def test_whoever_is_with_him_is_fair_to_think_about() -> None:
    from eidos.application.inner_stream import known_names, stray_name

    context = stream_context(snapshot(), ["Betty's smile again."], Cue("here", "The workshop"))
    assert context["with_him"] == ["Ellis"]
    assert stray_name("Ellis has a new wrench, shiny.", context, known_names(snapshot())) is None


def test_a_worn_out_motif_is_named_so_the_model_can_leave_it() -> None:
    from eidos.adapters.http_gateway import compact_context
    from eidos.application.inner_stream import worn_out

    recent = [
        "Oil smell's thick. Wonder if Beth knows Ellis is asking about Monday.",
        "Oil's thick in here. Beth might be telling Ellis about Monday.",
        "Oil smell's heavy. Beth and Ellis busy.",
    ]
    tired = worn_out(recent, {"Beth", "Ellis"})
    assert "oil" in tired and "thick" in tired and "monday" in tired
    assert "beth" not in tired and "ellis" not in tired  # people aren't motifs
    context = {**stream_context(snapshot(), recent, Cue("here", "The workshop")), "worn_out": tired}
    assert compact_context("murmur", context)["avoid_words"] == tired


def test_the_stream_steps_aside_while_his_life_needs_the_same_model(tmp_path) -> None:
    gateway = Thinker()
    busy = [True]
    stream = InnerStream(
        SQLiteInnerStream(tmp_path / "world.sqlite3"),
        gateway,
        lambda: (snapshot(), True),
        yield_to=lambda: busy[0],
    )
    stream.step()
    assert stream.state == "making way" and gateway.requests == []
    busy[0] = False
    stream.step()
    assert len(gateway.requests) == 1


def test_someone_his_mind_went_to_a_few_thoughts_ago_is_still_on_it(tmp_path) -> None:
    class Rowan(Thinker):
        def __init__(self) -> None:
            super().__init__()
            self.lines = iter(["Rowan's seeing someone, I reckon.", "Wonder if Rowan's happy."])

    world = snapshot()
    world["people"] = [*world["people"], {"name": "Rowan", "location_id": "park"}]
    stream = InnerStream(
        SQLiteInnerStream(tmp_path / "world.sqlite3"), Rowan(), lambda: (world, True)
    )
    stream._tried.append("Rowan's seeing someone")
    stream.step()
    stream.step()
    assert [t.text for t in stream.store.recent(2)] == [
        "Wonder if Rowan's happy.",
        "Rowan's seeing someone, I reckon.",
    ]


def test_bookkeeping_is_not_a_memory_his_mind_drifts_to() -> None:
    world = snapshot()
    world["memories"] = [
        {"text": "Started the planned activity: Tune the block plane.", "owner": "pathos"},
        {"text": "Beth Pritchard smiles, offering Pathos a cup of coffee.", "owner": "pathos"},
        {"text": "You sent a message: How are you?", "owner": "pathos"},
        {"text": "Rowan told me their mum's not been well.", "owner": "pathos"},
    ]
    memories = [cue.text for cue in cues(world) if cue.kind == "memory"]
    assert memories == ["Rowan told me their mum's not been well."]


def test_a_passing_thought_has_a_felt_tone() -> None:
    from eidos.application.inner_stream import felt_tone

    assert felt_tone("Rowan's mum sounds awful. Worried about him.") < 0
    assert felt_tone("Lovely evening. Glad I finished the plane.") > 0
    assert felt_tone("The bus is at ten past.") == 0.0


def test_how_his_thoughts_felt_moves_his_mood_at_the_quarter_hour(tmp_path) -> None:
    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(10)
    before = life._project_state(life.history()).valence
    assert life.pulse_inner_stream("Worried sick about Rowan's mum. Awful.", "m", -0.8)
    after = life._project_state(life.history()).valence
    assert after < before
    episode = next(e for e in reversed(life.history()) if e.kind == "affect.episode_started")
    assert episode.payload["source_kind"] == "thought.recorded"


def test_his_named_emotion_follows_his_feelings_within_the_quarter_hour(tmp_path) -> None:
    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(10)
    life.pulse_inner_stream("Worried sick. Awful, stuck, gutted.", "m", -0.9)
    snapshot = life.snapshot()
    assert snapshot["emotion"]["valence"] == snapshot["pathos"]["valence"]


def test_the_stream_knows_who_people_are_to_him() -> None:
    from eidos.adapters.http_gateway import compact_context

    world = snapshot()
    world["people"] = [
        {"id": "ellis", "name": "Ellis", "location_id": "cafe", "occupation": "Repair artist"},
        {"id": "mara", "name": "Mara", "location_id": "cafe", "occupation": "Café owner"},
    ]
    context = stream_context(world, ["Ellis should be home soon."], Cue("here", "The flat"))
    assert context["who_is_who"] == {"Ellis": "repair artist; he/him"}
    assert compact_context("murmur", context)["who_is_who"] == {"Ellis": "repair artist; he/him"}


def test_the_stream_knows_when_he_is_alone_and_where_his_family_is() -> None:
    from eidos.adapters.http_gateway import compact_context

    world = snapshot()
    world["people"] = []
    world["selfhood"] = {
        "family": [{"who": "Mum (Helen Shaw)", "relation": "mother", "about": "Gardens in Wye."}]
    }
    context = stream_context(world, ["Mum's packing for work."], Cue("here", "The flat"))
    assert "at home in Wye" in context["who_is_who"]["Mum"]
    assert compact_context("murmur", context)["with_him"] == "nobody; he's on his own"


def test_explaining_who_someone_is_doesnt_put_them_on_his_mind() -> None:
    from eidos.application.inner_stream import known_names, stray_name

    world = snapshot()
    world["people"] = [{"name": "Rowan", "location_id": "park", "occupation": "Illustrator"}]
    context = stream_context(world, ["Rowan's quiet lately."], Cue("money", "£420"))
    assert "Rowan" in context["who_is_who"]
    assert stray_name("Rowan's still quiet.", context, known_names(world)) == "Rowan"
