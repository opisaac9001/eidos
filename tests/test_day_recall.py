"""Asked about a particular time, he thinks back to that time."""

from datetime import datetime, timedelta, timezone

from eidos.application.day_recall import asked_about, recall_of_that_time, that_time
from eidos.domain.events import DomainEvent

# A Wednesday afternoon.
NOW = datetime(2026, 8, 26, 15, 0, tzinfo=timezone.utc)


def memory(at, text, importance=0.4, **extra):
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {"text": text, "importance": importance, "simulated_at": at.isoformat(), **extra},
    )


def span(text):
    found = asked_about(text, NOW)
    assert found is not None, text
    start, end, label = found
    return start, end, label


def test_the_time_being_asked_about() -> None:
    start, end, label = span("What did you do Monday evening?")
    assert (start, end) == (datetime(2026, 8, 24, 17, tzinfo=timezone.utc),
                            datetime(2026, 8, 25, 0, tzinfo=timezone.utc))  # fmt: skip
    assert label == "Monday evening"
    start, end, _ = span("how was last night?")
    assert start == datetime(2026, 8, 25, 18, tzinfo=timezone.utc)
    assert end == datetime(2026, 8, 26, 4, tzinfo=timezone.utc)
    start, end, _ = span("what were you up to yesterday?")
    assert start.day == 25 and end.day == 26 and end.hour == 0
    start, end, _ = span("good morning? what did you do this morning")
    assert start.hour == 5 and end.hour == 12 and start.day == 26
    start, end, _ = span("what did you get up to at the weekend?")
    assert start == datetime(2026, 8, 22, tzinfo=timezone.utc) and end.day == 24
    start, _, _ = span("did you go anywhere on Wednesday?")
    assert start.day == 26  # today
    start, _, _ = span("what did you do last Wednesday?")
    assert start.day == 19


def test_not_a_question_about_the_past() -> None:
    assert asked_about("shall we get coffee on Saturday morning?", NOW) is None
    assert asked_about("I love Mondays", NOW) is None
    assert asked_about("what are you doing this evening?", NOW) is None  # not yet happened


def test_what_he_remembers_of_it_in_order() -> None:
    monday = datetime(2026, 8, 24, tzinfo=timezone.utc)
    history = [
        memory(monday + timedelta(hours=9), "Fixed the lamp from the market stall."),
        memory(monday + timedelta(hours=19), "Walked along the river with Mara.", 0.7),
        memory(monday + timedelta(hours=20), "A dream about chisels.", category="dream"),
        memory(monday + timedelta(hours=21), "Ellis said the shop's busy.", owner="ellis"),
        memory(monday + timedelta(hours=22), "Put a record on and read."),
        memory(monday + timedelta(days=1, hours=19), "Tuesday's tea."),
    ]
    then = recall_of_that_time(history, "what did you do Monday evening?", NOW)
    assert then is not None and then["when"] == "Monday evening"
    assert then["what_he_remembers"] == [
        "Monday 19:00: Walked along the river with Mara.",
        "Monday 22:00: Put a record on and read.",
    ]


def test_nothing_stands_out_is_said_as_such() -> None:
    then = recall_of_that_time([], "how was Monday?", NOW)
    assert then == {"when": "Monday", "what_he_remembers": []}


def test_the_most_important_kept_when_theres_a_lot() -> None:
    day = datetime(2026, 8, 25, 8, tzinfo=timezone.utc)
    history = [memory(day + timedelta(minutes=20 * i), f"thing {i}", 0.3) for i in range(20)]
    history.append(memory(day + timedelta(hours=3, minutes=5), "Rowan rang about their mum.", 0.9))
    kept = that_time(history, day, day + timedelta(hours=16), limit=5)
    assert len(kept) == 5 and any("Rowan" in line for line in kept)
    assert kept == sorted(kept, key=lambda line: line.split(": ")[0][-5:])
