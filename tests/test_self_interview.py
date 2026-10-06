"""Asked about his own week, his answers are checked against what happened, and the
asking never becomes part of his life."""

import asyncio
from datetime import datetime, timedelta, timezone

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.application.self_interview import Question, interview_report, questions_for, score
from eidos.domain.events import DomainEvent

NOW = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)


def memory(text: str, at: datetime) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {"text": text, "owner": "pathos", "simulated_at": at.isoformat()},
    )


def test_questions_come_from_his_actual_week() -> None:
    evening = (NOW - timedelta(days=2)).replace(hour=19)
    history = [
        memory("Went to the Crown with Ellis and lost at darts again.", evening),
        DomainEvent(
            "npc.encountered",
            "pathos",
            {"person_id": "mara", "text": "Mara waves.", "simulated_at": NOW.isoformat()},
        ),
        DomainEvent(
            "sleep.started", "pathos", {"simulated_at": (NOW - timedelta(hours=10)).isoformat()}
        ),
        DomainEvent(
            "sleep.ended", "pathos", {"simulated_at": (NOW - timedelta(hours=5)).isoformat()}
        ),
    ]
    asked = {q.topic: q for q in questions_for(history, NOW, {"mara": "Mara", "ellis": "Ellis"})}
    assert asked["an evening"].text == f"What did you get up to on {evening:%A} evening?"
    assert asked["who he's seen"].names == ("Mara",)
    assert "sleep" in asked


def test_answers_are_grounded_vague_or_contradicted() -> None:
    darts = Question("an evening", "?", ("Went to the Crown with Ellis and lost at darts again.",))
    assert score(darts, "Pub with Ellis, the Crown. Lost at darts, as usual.") == "grounded"
    assert score(darts, "Not sure, quiet one I think.") == "vague"
    sleep = Question("sleep", "?", ("badly short",), contradictions=("slept great",))
    assert score(sleep, "Slept great actually.") == "contradicted"
    report = interview_report([(darts, "Pub with Ellis, lost at darts."), (sleep, "Slept great.")])
    assert report["score"] == 0.5 and report["contradicted"] == 1


def test_asking_him_leaves_no_trace_in_his_life(tmp_path) -> None:
    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(24)
    life.advance(6)
    before = len(life.history())
    prompts = life.interview_prompts()
    assert prompts
    report = asyncio.run(life.interview_answers(prompts))
    assert report["asked"] == len(prompts)
    assert all(item["answer"] for item in report["answers"])
    assert len(life.history()) == before
