"""A change to how a role is asked is tried on real moments before his life gets it."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from eidos.adapters import http_gateway
from eidos.adapters.harness_runner import asked_as, load_samples, run
from eidos.application.harness_probe import Outcome, Variant, judge, verdict
from eidos.ports.model_gateway import ModelRequest, ModelResponse

ENCOUNTER = {
    "time": "2026-09-08T16:00:00+00:00",
    "person": "Stuart Hart",
    "location": "market-hall",
    "setting": "Patrick is at Market Hall",
}
SCENE = {
    "time": "2026-09-08T16:00:00+00:00",
    "person": "Ellis",
    "scene_mode": True,
    "scene_speaker": "ellis",
    "scene_topic": "Patrick's own project (his, nobody else's): a small atlas of town sounds",
    "setting": "Patrick has dropped in at Ellis's repair workshop",
    "prior_turns": [],
}


def _said(text: str) -> str:
    return json.dumps({"text": text})


def test_the_checks_say_what_would_be_turned_away() -> None:
    assert judge("firmament", ENCOUNTER, _said("Stuart waves from the cheese stall.")) == []
    assert judge("firmament", ENCOUNTER, _said("Someone waves from a stall.")) == ["missing_actor"]
    assert "leak" in judge("firmament", ENCOUNTER, _said("Stuart talks about the sounds of Eidos."))
    assert "claims_his_project" in judge(
        "firmament",
        SCENE,
        _said("I've been working on this small atlas of town sounds. Any tips, Patrick?"),
    )
    assert (
        judge("firmament", SCENE, _said("How's that atlas of town sounds coming on, Patrick?"))
        == []
    )


def test_only_a_clear_improvement_is_adopted() -> None:
    bad = [Outcome(i, "x", ("missing_actor",)) for i in range(4)] + [
        Outcome(i, "y", ()) for i in range(6)
    ]
    good = [Outcome(i, "y", ()) for i in range(10)]
    assert verdict(bad, good) == "adopt"
    assert verdict(good, good).startswith("keep current")
    assert verdict(good, bad).startswith("keep current")


def test_a_variant_changes_the_role_only_for_the_probe() -> None:
    before_prompt = http_gateway.ROLE_PROMPTS["firmament"]
    before_fields = tuple(http_gateway.ROLE_FIELDS["firmament"])
    variant = Variant("firmament", "try", prompt_append="Use first names.", fields_add=("x",))
    with asked_as(variant):
        assert http_gateway.role_prompt("firmament").endswith("Use first names.")
        assert "x" in http_gateway.role_fields("firmament")
        # The shared tables his life's calls read are untouched, even mid-probe.
        assert http_gateway.ROLE_PROMPTS["firmament"] == before_prompt
    assert http_gateway.role_prompt("firmament") == before_prompt
    assert tuple(http_gateway.role_fields("firmament")) == before_fields


def _database(path: Path, contexts: list[dict]) -> Path:
    db = path / "jobs.sqlite3"
    connection = sqlite3.connect(db)
    connection.execute(
        "create table cognition_jobs (capability text, context_json text, status text, result text)"
    )
    connection.executemany(
        "insert into cognition_jobs values (?, ?, ?, ?)",
        [
            ("firmament", json.dumps(context), "completed", "Someone waves from a stall.")
            for context in contexts
        ],
    )
    connection.commit()
    connection.close()
    return db


class _Model:
    """Leaves Stuart out unless asked to use first names, the way the real ones did."""

    model = "fake"

    async def generate(self, request: ModelRequest) -> ModelResponse:
        careful = http_gateway.role_prompt("firmament").endswith("Use first names.")
        text = "Stuart waves from the cheese stall." if careful else "Someone waves from a stall."
        return ModelResponse(_said(text), "fake", "fake", "stop", 1, 1)


def test_a_probe_compares_the_two_ways_on_the_same_moments(tmp_path: Path) -> None:
    contexts = [{**ENCOUNTER, "time": f"2026-09-08T1{n}:00:00+00:00"} for n in range(5)]
    db = _database(tmp_path, contexts)
    assert len(load_samples(db, "firmament", 3)) == 3
    assert load_samples(db, "firmament", 10, grep="nobody") == []
    variant_file = tmp_path / "first-names.json"
    variant_file.write_text(
        json.dumps(
            {
                "role": "firmament",
                "name": "first-names",
                "why": "Stuart left out",
                "prompt_append": "Use first names.",
            }
        )
    )
    lessons = tmp_path / "LESSONS.md"
    result = run(
        _Model(),
        db,
        "firmament",
        variant_path=variant_file,
        samples=5,
        repeats=1,
        grep=None,
        out=tmp_path / "out",
        lessons=lessons,
    )
    assert result["current"]["turned_away"] == 1.0
    assert result["candidate"]["turned_away"] == 0.0
    assert result["verdict"] == "adopt"
    assert result["where_they_differ"]
    assert (tmp_path / "out" / "firmament-first-names.json").exists()
    assert "first-names" in lessons.read_text() and "adopt" in lessons.read_text()
    # And the live prompt is as it was.
    assert not http_gateway.role_prompt("firmament").endswith("Use first names.")


def test_more_roles_are_judged_and_names_from_nowhere_are_caught() -> None:
    from eidos.application.harness_probe import stray_name

    text_context = {"to": "Ellis", "why_hes_getting_in_touch": ["the clock"]}
    assert judge("pathos_text", text_context, _said("How's the clock coming on?")) == []
    assert "signed_off" in judge("pathos_text", text_context, _said("Pint later? Cheers, Patrick"))
    assert "emoji" in judge("pathos_text", text_context, _said("Pint later? 🍺"))
    assert "third_person" in judge("murmur", {}, json.dumps({"text": "Patrick wonders about tea."}))
    names = ["Mara Bell", "Ellis Hart", "Rowan Ames"]
    assert stray_name("Mara would laugh at this.", {"cue": "the kettle"}, names) == "Mara"
    assert stray_name("Ellis's clock again.", text_context, names) is None
    assert "stray_name" in judge(
        "firmament", ENCOUNTER, _said("Stuart waves and says Rowan was asking after him."), names
    )


def test_quality_and_margins_say_more_than_the_rate() -> None:
    from eidos.application.harness_probe import holds_up, interval, quality

    contexts = [ENCOUNTER, ENCOUNTER]
    alike = [Outcome(0, "Stuart waves hello.", ()), Outcome(1, "Stuart waves hello.", ())]
    varied = [
        Outcome(0, "Stuart waves from the cheese stall.", ()),
        Outcome(1, "Stuart grins and holds up a jar of honey.", ()),
    ]
    assert (
        quality(varied, contexts)["distinct_openings"]
        > quality(alike, contexts)["distinct_openings"]
    )
    low, high = interval([Outcome(i, "x", ("missing_actor",) if i < 3 else ()) for i in range(10)])
    assert low < 0.3 < high
    # Better overall but worse on half the moments doesn't hold up.
    before = [Outcome(i, "x", ("bad",) if i % 2 == 0 else ()) for i in range(10)]
    after = [Outcome(i, "x", ("bad",) if i == 1 else ()) for i in range(10)]
    assert not holds_up(before, after)


class _Editor(_Model):
    async def generate(self, request: ModelRequest) -> ModelResponse:
        if request.capability == "harness_editor":
            body = {
                "variants": [
                    {"name": "First Names!", "why": "Stuart was left out.",
                     "prompt_append": "Use first names."},
                    {"name": "say-less", "why": "Shorter.", "prompt_append": "Be brief."},
                ]
            }  # fmt: skip
            return ModelResponse(json.dumps(body), "fake", "fake", "stop", 1, 1)
        return await super().generate(request)


def test_the_editor_proposes_and_only_a_winner_is_suggested(tmp_path: Path) -> None:
    from eidos.adapters.harness_runner import improve

    contexts = [{**ENCOUNTER, "time": f"2026-09-08T1{n}:00:00+00:00"} for n in range(6)]
    db = _database(tmp_path, contexts)
    lessons = tmp_path / "LESSONS.md"
    result = improve(
        _Editor(), db, "firmament", samples=6, repeats=1, proposals=2, grep=None,
        out=tmp_path / "out", lessons=lessons,
    )  # fmt: skip
    names = [c["name"] for c in result["candidates"]]
    assert names == ["proposed-first-names", "proposed-say-less"]
    assert result["best"]["name"] == "proposed-first-names"
    assert (tmp_path / "out" / "firmament-proposed-first-names.json").exists()
    assert lessons.read_text().count("## ") == 2


def test_models_can_be_compared_on_the_same_moments(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from eidos.adapters.harness_runner import compare_models

    class _Careless:
        model = "careless"

        async def generate(self, request: ModelRequest) -> ModelResponse:
            return ModelResponse(
                _said("Someone waves from a stall."), "careless", "fake", "stop", 1, 1
            )

    class _Careful(_Careless):
        async def generate(self, request: ModelRequest) -> ModelResponse:
            return ModelResponse(
                _said("Stuart waves from the cheese stall."), "careful", "fake", "stop", 1, 1
            )

    class _Configured:
        def entries(self):
            return {
                "small": SimpleNamespace(gateway=_Careless()),
                "big": SimpleNamespace(gateway=_Careful()),
            }

        def chain(self, role):
            return ["small", "big"]

    db = _database(tmp_path, [ENCOUNTER])
    result = compare_models(
        _Configured(), db, "firmament", ["small", "big"], samples=1, repeats=2, grep=None
    )
    assert result["models"]["small"]["turned_away"] == 1.0
    assert result["models"]["big"]["turned_away"] == 0.0
    assert result["now_tries"] == ["small", "big"]


def test_the_checks_can_be_checked_on_answers_already_given(tmp_path: Path) -> None:
    from eidos.application.harness_probe import audit

    recorded = [
        (ENCOUNTER, "Stuart waves from the cheese stall."),
        (ENCOUNTER, json.dumps({"text": "Someone waves from a stall."})),
    ]
    result = audit("firmament", recorded)
    assert result["answers"] == 2
    assert result["would_be_turned_away"] == 0.5
    assert result["problems"] == {"missing_actor": 1}


def test_a_night_measures_each_role_and_keeps_the_trend(tmp_path: Path) -> None:
    from eidos.adapters.harness_runner import latest_nights, nightly

    contexts = [{**ENCOUNTER, "time": f"2026-09-08T1{n}:00:00+00:00"} for n in range(6)]
    db = _database(tmp_path, contexts)
    folder = tmp_path / "harness"
    night = nightly(_Editor(), db, folder, names=[], when="2026-09-09T02:00:00+00:00")
    assert night["roles"]["firmament"]["turned_away"] == 1.0
    # The worst role got suggestions; none is adopted by the night itself.
    assert night["suggestions"]["best"]["name"] == "proposed-first-names"
    assert not http_gateway.role_prompt("firmament").endswith("Use first names.")
    seen = latest_nights(folder)
    assert seen["last"]["when"] == "2026-09-09T02:00:00+00:00"
    assert seen["trend"][-1]["suggested"] == "proposed-first-names"


def test_a_change_that_makes_him_much_more_alike_is_not_adopted() -> None:
    from eidos.application.harness_probe import trade_offs, variety

    contexts = [ENCOUNTER] * 10
    current = [
        Outcome(i, f"Stuart {w} from the stall.", ("missing_actor",) if i < 5 else ())
        for i, w in enumerate(
            "waves grins nods laughs calls shouts beams points smiles winks".split()
        )
    ]
    samey = [Outcome(i, "Stuart waves from the stall.", ()) for i in range(10)]
    assert variety(current, samey, contexts) < 0.6
    assert (
        verdict(current, samey, variety(current, samey, contexts))
        == "keep current: much more alike"
    )
    assert "openings less varied" in trade_offs(current, samey, contexts)


def test_a_thought_is_judged_by_the_probe_exactly_as_the_stream_judges_it() -> None:
    from eidos.application.inner_stream import JUDGE_KEY, StreamJudge, turned_away_for

    judge = StreamJudge(
        recent=("Kettle's taking ages.",),
        earlier=("Kettle's taking ages.", "Rain on the skylight."),
        names=("Mara", "Ellis"),
        cue_text="the kettle",
    )
    context = {"location": "at home", "cue": "the kettle", JUDGE_KEY: judge.payload()}
    assert StreamJudge.from_payload(judge.payload()) == judge
    for text, kind in (
        ("Kettle's taking ages.", "repeat"),
        ("Mara would laugh at this kettle.", "stray_name"),
        ("Pathos needs a new kettle.", "third_person"),
    ):
        said = json.dumps({"text": text})
        assert turned_away_for(text, context, judge) is not None
        assert kind in judge_kinds(said, context)
    fine = "Steam on the window. Nearly there."
    assert turned_away_for(fine, context, judge) is None
    assert judge_kinds(json.dumps({"text": fine}), context) == []


def judge_kinds(content: str, context: dict) -> list[str]:
    return judge("murmur", context, content)
