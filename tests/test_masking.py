"""'Fine, yeah' when he isn't, and owning up later."""

from datetime import datetime, timedelta, timezone

from eidos.application.masking import masking_context, what_is_weighing
from eidos.domain.events import DomainEvent

AT = datetime(2027, 5, 10, 19, tzinfo=timezone.utc)


def fell_out(at: datetime) -> DomainEvent:
    return DomainEvent(
        "friend.falling_out",
        "pathos",
        {"person_id": "mara", "stage": "fell_out", "text": "…", "simulated_at": at.isoformat()},
    )


def test_nothing_to_hide_means_nothing_added() -> None:
    assert what_is_weighing([], AT, 0.2) is None
    assert masking_context([], AT, "how are you?", 0.2, "friend", "r1") == ({}, [])
    assert what_is_weighing([], AT, -0.5)  # a low patch counts


def test_closer_friends_hear_the_truth_more_often() -> None:
    history = [fell_out(AT - timedelta(days=1))]

    def honest_share(bond):
        told = 0
        for n in range(200):
            _, events = masking_context(history, AT, "you alright?", 0.0, bond, f"r{n}")
            told += events[0].kind == "feeling.shared"
        return told / 200

    assert honest_share(None) < honest_share("friend") < honest_share("closest")
    assert honest_share("closest") > 0.85
    assert honest_share(None) < 0.25


def test_he_owns_up_next_time_you_talk() -> None:
    history = [fell_out(AT - timedelta(days=1))]
    masked = next(
        events[0]
        for n in range(100)
        for _, events in [masking_context(history, AT, "how are you", 0.0, "friend", f"m{n}")]
        if events[0].kind == "feeling.masked"
    )
    history.append(masked)
    same_day, nothing = masking_context(history, AT + timedelta(hours=1), "hey", 0.0, "friend", "x")
    assert same_day == {} and nothing == []
    later = AT + timedelta(days=1)
    context, events = masking_context(history, later, "hey", 0.0, "friend", "y")
    assert "owes_honesty" in context and events[0].kind == "feeling.admitted"
    history += events
    assert masking_context(history, later + timedelta(hours=2), "hey", 0.0, "friend", "z") == (
        {},
        [],
    )
    # Someone he's not close to never gets the confession.
    stranger = masking_context(history[:-1], later, "hey", 0.0, None, "q")
    assert stranger == ({}, [])
