"""'Quiet' only when nothing's colouring the day: otherwise he's worried, or pleased."""

from datetime import datetime, timedelta, timezone

from eidos.application.feelings import AROSE, mood_from_feelings
from eidos.domain.emotions import emotion_sample_events
from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState

AT = datetime(2026, 8, 26, 15, tzinfo=timezone.utc)


def worry(strength, hours_ago=0):
    return DomainEvent(
        AROSE,
        "pathos",
        {
            "feeling_id": "worry:rowan",
            "kind": "worry",
            "about": "Rowan",
            "intensity": strength,
            "simulated_at": (AT - timedelta(hours=hours_ago)).isoformat(),
        },
    )


def label(history, valence, arousal=0.35):
    state = PathosState(simulated_at=AT, awake=True, valence=valence, arousal=arousal)
    sampled = emotion_sample_events(history, state, AT, felt=mood_from_feelings(history, AT))
    return sampled[0].payload["label"]


def test_a_neutral_mood_takes_its_name_from_what_hes_feeling() -> None:
    assert label([], 0.0) == "quiet"
    assert label([worry(0.6)], 0.0) == "worried"
    # A feeling long faded doesn't name the day.
    assert label([worry(0.3, hours_ago=200)], 0.0) == "quiet"


def test_a_real_mood_keeps_its_own_name() -> None:
    assert label([worry(0.6)], -0.4, 0.3) == "sadness"
    assert label([worry(0.6)], 0.2) == "contentment"
