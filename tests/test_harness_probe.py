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
        assert http_gateway.ROLE_PROMPTS["firmament"].endswith("Use first names.")
        assert "x" in http_gateway.ROLE_FIELDS["firmament"]
    assert http_gateway.ROLE_PROMPTS["firmament"] == before_prompt
    assert tuple(http_gateway.ROLE_FIELDS["firmament"]) == before_fields


def _database(path: Path, contexts: list[dict]) -> Path:
    db = path / "jobs.sqlite3"
    connection = sqlite3.connect(db)
    connection.execute("create table cognition_jobs (capability text, context_json text)")
    connection.executemany(
        "insert into cognition_jobs values (?, ?)",
        [("firmament", json.dumps(context)) for context in contexts],
    )
    connection.commit()
    connection.close()
    return db


class _Model:
    """Leaves Stuart out unless asked to use first names, the way the real ones did."""

    model = "fake"

    async def generate(self, request: ModelRequest) -> ModelResponse:
        careful = http_gateway.ROLE_PROMPTS["firmament"].endswith("Use first names.")
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
    assert not http_gateway.ROLE_PROMPTS["firmament"].endswith("Use first names.")
