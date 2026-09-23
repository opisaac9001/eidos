from datetime import datetime, timedelta, timezone
from uuid import UUID

from eidos.application.causal_opportunities import fresh_cause
from eidos.application.cognitive_workspace import cognitive_workspace, recent_inner_stream
from eidos.application.inner_life import active_dream_inspirations, waking_dream_events
from eidos.application.semantic_quality import semantic_quality_findings
from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState

NOW = datetime(2026, 2, 3, 8, tzinfo=timezone.utc)


def thought(text, minutes=0, **extra):
    return DomainEvent(
        "thought.recorded",
        "pathos",
        {"text": text, "simulated_at": (NOW + timedelta(minutes=minutes)).isoformat(), **extra},
    )


def test_thoughts_fade_without_deleting_inspection_history():
    history = [thought("The tea's still warm.")]
    fresh = cognitive_workspace(history, NOW)[0]["salience"]
    later = cognitive_workspace(history, NOW + timedelta(minutes=20))[0]["salience"]
    assert later < fresh / 2
    assert recent_inner_stream(history, NOW) == ["The tea's still warm."]
    assert recent_inner_stream(history, NOW + timedelta(minutes=30)) == []
    assert cognitive_workspace(history, NOW + timedelta(hours=1)) == []
    assert (
        fresh_cause(history, NOW + timedelta(minutes=30), frozenset({"thought.recorded"})) is None
    )
    assert fresh_cause(history, NOW, frozenset({"thought.recorded"})) == history[0]
    assert len(history) == 1 and history[0].kind == "thought.recorded"


def test_private_thought_can_be_a_small_fragment_without_explicit_i():
    assert "lost_first_person_role" not in semantic_quality_findings(
        "murmur", "Tea's gone cold.", {}
    )
    assert "lost_first_person_role" in semantic_quality_findings(
        "murmur", "Pathos considered the meaning of tea.", {}
    )


def test_inner_stream_excludes_private_future_and_old_material():
    history = [
        thought("old", -60),
        thought("Mara's private thought", owner="mara"),
        thought("future", 1),
        thought("one", -3),
        thought("two", -2),
        thought("three", -1),
    ]
    assert recent_inner_stream(history, NOW) == ["one", "two", "three"]
    assert all(
        item["content"] != "Mara's private thought" for item in cognitive_workspace(history, NOW)
    )


def test_most_dreams_pass_without_memory_or_inspiration_and_replay_stably():
    counts = {
        "dream.forgotten": 0,
        "dream.recalled": 0,
        "memory.recorded": 0,
        "dream.inspiration_considered": 0,
    }
    state = PathosState(awake=True)
    for index in range(1, 101):
        dream = DomainEvent(
            "dream.recorded",
            "pathos",
            {
                "text": "In a dream, the letter kept folding into a small boat and floating away.",
                "simulated_at": (NOW - timedelta(hours=2)).isoformat(),
            },
            event_id=UUID(int=index),
        )
        effect = DomainEvent(
            "dream.effect_scheduled",
            "pathos",
            {
                "source_dream_id": str(dream.event_id),
                "valence_delta": 0.03,
                "simulated_at": (NOW - timedelta(hours=2)).isoformat(),
            },
        )
        history = [dream, effect]
        events = waking_dream_events(history, state, NOW.isoformat())
        again = waking_dream_events(history, state, NOW.isoformat())
        assert [(e.kind, dict(e.payload)) for e in events] == [
            (e.kind, dict(e.payload)) for e in again
        ]
        assert waking_dream_events(history + events, state, NOW.isoformat()) == []
        assert waking_dream_events(history, PathosState(), NOW.isoformat()) == []
        for event in events:
            if event.kind in counts:
                counts[event.kind] += 1
            if event.kind == "memory.recorded":
                assert event.payload["factual"] is False and event.payload["category"] == "dream"
                assert event.payload["confidence"] < 1
            if event.kind == "dream.inspiration_considered":
                assert event.payload["action_authority"] is False
                assert active_dream_inspirations(events, NOW + timedelta(hours=1)) == []
        assert not any(
            e.kind in {"schedule.created", "intention.adopted", "goal.created"} for e in events
        )
        if any(e.kind == "dream.forgotten" for e in events):
            assert not any(
                e.kind in {"dream.recalled", "memory.recorded", "dream.inspiration_considered"}
                for e in events
            )
            assert any(e.kind == "affect.changed" for e in events)
    assert counts["dream.forgotten"] > 50
    assert 0 < counts["memory.recorded"] < counts["dream.recalled"]
    assert 0 < counts["dream.inspiration_considered"] < counts["dream.recalled"]
