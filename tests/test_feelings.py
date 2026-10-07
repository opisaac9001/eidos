"""He feels several things at once, each about something, fading at its own pace."""

from datetime import datetime, timedelta, timezone

from eidos.application.feelings import (
    AROSE,
    RENEWED,
    SETTLED,
    coping_thoughts,
    feeling_events,
    feelings_view,
    live_feelings,
)
from eidos.application.inner_stream import cues
from eidos.domain.events import DomainEvent

AT = datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc)
NAMES = {"rowan": "Rowan", "beth": "Beth Pritchard"}


def opened(kind: str, at: datetime, **extra) -> DomainEvent:
    return DomainEvent(
        "concern.opened",
        "pathos",
        {
            "concern_id": f"concern:{kind}",
            "concern_kind": kind,
            "importance": 0.72,
            "text": "Something coming up, coming up.",
            "simulated_at": at.isoformat(),
            **extra,
        },
    )


def test_two_people_two_feelings_at_once() -> None:
    history = [
        opened("worry", AT - timedelta(minutes=10), person_id="rowan"),
        opened("loss", AT - timedelta(minutes=5), person_id="beth"),
    ]
    history += feeling_events(history, AT, names=NAMES)
    phrases = [f["feeling"] for f in feelings_view(history, AT)]
    assert "worried about Rowan" in phrases and "sad about Beth leaving" in phrases


def test_feelings_fade_at_their_own_pace_and_settle() -> None:
    soaked = DomainEvent(
        "happening.occurred",
        "pathos",
        {"kind": "caught_in_rain", "simulated_at": (AT - timedelta(minutes=5)).isoformat()},
    )
    worry = opened("worry", AT - timedelta(minutes=5), person_id="rowan")
    history = [soaked, worry]
    history += feeling_events(history, AT, names=NAMES)
    later = AT + timedelta(hours=10)
    kinds = {f.kind for f in live_feelings(history, later)}
    assert "worry" in kinds and "irritation" not in kinds  # annoyance passes in hours
    settled = feeling_events(history, later, names=NAMES)
    assert any(
        e.kind == SETTLED and e.payload["feeling_id"].startswith("irritation") for e in settled
    )


def test_the_same_cause_again_renews_a_feeling_not_a_new_one() -> None:
    history = [opened("worry", AT - timedelta(minutes=5), person_id="rowan")]
    history += feeling_events(history, AT, names=NAMES)
    heard = DomainEvent(
        "gossip.heard",
        "pathos",
        {
            "holder_id": "pathos",
            "subject_id": "rowan",
            "story": "family_worry",
            "simulated_at": (AT + timedelta(hours=5)).isoformat(),
        },
    )
    history.append(heard)
    again = feeling_events(history, AT + timedelta(hours=5, minutes=10), names=NAMES)
    assert [e.kind for e in again if e.kind in {AROSE, RENEWED}] == [RENEWED]


def test_coping_turns_feelings_into_pulls_and_thoughts_follow_them() -> None:
    history = [opened("worry", AT - timedelta(minutes=5), person_id="rowan")]
    history += feeling_events(history, AT, names=NAMES)
    urges = coping_thoughts(history, AT)
    assert urges == ["I'm worried about Rowan. Should check in on Rowan."]
    snapshot = {
        "time": AT.isoformat(),
        "pathos": {"location_id": "home", "awake": True},
        "people": [],
        "feelings": feelings_view(history, AT),
    }
    assert any(c.kind == "feeling" and c.text == "worried about Rowan" for c in cues(snapshot))


def test_a_worry_ends_when_things_get_better() -> None:
    worry = opened("worry", AT - timedelta(minutes=5), person_id="rowan")
    history = [worry]
    history += feeling_events(history, AT, names=NAMES)
    better = DomainEvent(
        "concern.resolved",
        "pathos",
        {
            "concern_id": "concern:worry",
            "resolution_kind": "things_got_better",
            "simulated_at": (AT + timedelta(days=1)).isoformat(),
        },
    )
    history.append(better)
    later = feeling_events(history, AT + timedelta(days=1, minutes=10), names=NAMES)
    assert any(e.kind == SETTLED and e.payload["feeling_id"] == "worry:rowan" for e in later)
    assert any(e.kind == AROSE and e.payload["kind"] == "relief" for e in later)
