"""His inner monologue keeps running between the quarter-hour pulses."""

import json
import random

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
    available = [Cue("here", "the workshop"), Cue("body", "hungry")]
    assert all(choose_cue(available, ["here"], rng).kind == "body" for _ in range(20))
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
