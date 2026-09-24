"""Views on the town: a row every few months, his view on it, and the council's say."""

from datetime import date, datetime, timedelta, timezone

from eidos.adapters.standin_gateway import _standin_town_reply
from eidos.application.appraisal import _AppraisalIndex, _effect
from eidos.application.economy import financial_foundation_events
from eidos.application.town_issues import (
    BY_ID,
    DECISION_HOUR,
    GAP_DAYS,
    GAP_SPREAD,
    HOURS,
    ISSUES,
    REVIEW_HOUR,
    SETTLED_FOR,
    _raise,
    lean_from_values,
    town_issue_events,
    town_issues_context,
    views,
)
from eidos.domain.events import DomainEvent
from eidos.domain.selfhood import STARTING_VALUES

OPENED = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
VALUES = dict(STARTING_VALUES)


def at(day: date, hour: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)


def live(
    history: list[DomainEvent],
    start: date,
    days: int,
    *,
    values=VALUES,
    venue="council-office",
    attend=True,
    with_ellis=False,
) -> list[DomainEvent]:
    """Drive the town's rows hour by hour; he turns up to any meeting he booked."""
    booked = {
        e.payload["schedule_id"]: datetime.fromisoformat(e.payload["starts_at"]).date()
        for e in history
        if e.kind == "schedule.created"
    }
    for offset in range(days):
        day = start + timedelta(days=offset)
        for hour in sorted(HOURS):
            calendar = {
                schedule_id: "completed" if attend and on <= day else "scheduled"
                for schedule_id, on in booked.items()
            }
            output = town_issue_events(
                history,
                at(day, hour),
                awake=True,
                values=values,
                calendar=calendar,
                venue=venue,
                with_ellis=with_ellis,
            )
            for event in output:
                if event.kind == "schedule.created":
                    booked[event.payload["schedule_id"]] = datetime.fromisoformat(
                        event.payload["starts_at"]
                    ).date()
            history = [*history, *output]
    return history


def raised_on(issue_id: str, day: date, values=VALUES, venue="council-office"):
    history = financial_foundation_events([], OPENED)
    return [*history, *_raise(BY_ID[issue_id], at(day, 13), values, venue)]


def stages(history) -> list[tuple[str, str]]:
    return [(e.payload["issue_id"], e.payload["stage"]) for e in history if e.kind == "town.issue"]


def test_an_issue_every_four_to_six_months_never_two_at_once() -> None:
    history = live(financial_foundation_events([], OPENED), OPENED.date(), 1000)
    raised = [e for e in history if e.kind == "town.issue" and e.payload["stage"] == "raised"]
    times = [datetime.fromisoformat(e.payload["simulated_at"]) for e in raised]
    assert len(raised) >= 5
    assert times[0] - OPENED >= SETTLED_FOR
    for earlier, later in zip(times, times[1:]):
        assert (
            timedelta(days=GAP_DAYS) <= later - earlier <= timedelta(days=GAP_DAYS + GAP_SPREAD + 1)
        )
    assert len({e.payload["issue_id"] for e in raised}) == len(raised) == len(ISSUES)
    # Each is raised, met over and decided before the next one comes up.
    sequence = stages(history)
    for index in range(0, len(sequence), 3):
        issue_id = sequence[index][0]
        assert sequence[index : index + 3] == [
            (issue_id, "raised"),
            (issue_id, "meeting"),
            (issue_id, "decided"),
        ]
    meeting = next(e for e in history if e.kind == "town.issue" and e.payload["stage"] == "meeting")
    assert meeting.payload["location_id"] == "council-office"


def test_nothing_before_he_has_been_in_town_a_few_months() -> None:
    history = live(financial_foundation_events([], OPENED), OPENED.date(), 99)
    assert stages(history) == []


def test_his_view_follows_his_values() -> None:
    for issue in ISSUES:
        favours = {value for value, _ in issue.for_values}
        opposes = {value for value, _ in issue.against_values}
        for_it = {v: 0.95 if v in favours else 0.05 for v in STARTING_VALUES}
        against_it = {v: 0.95 if v in opposes else 0.05 for v in STARTING_VALUES}
        assert lean_from_values(issue, for_it) > 0.25
        assert lean_from_values(issue, against_it) < -0.25
        for values, side in ((for_it, "for"), (against_it, "against")):
            history = raised_on(issue.issue_id, date(2026, 6, 3), values)
            formed = next(e for e in history if e.kind == "opinion.formed")
            assert formed.payload["side"] == side
            assert formed.payload["value_id"] in (favours if side == "for" else opposes)
            assert formed.payload["strength"] >= 0.5


def test_the_same_life_takes_the_same_view() -> None:
    first = raised_on("old-mill-flats", date(2026, 6, 3))
    again = raised_on("old-mill-flats", date(2026, 6, 3))
    lean = [e.payload["lean"] for e in first if e.kind == "opinion.formed"]
    assert lean == [e.payload["lean"] for e in again if e.kind == "opinion.formed"]


def test_a_meeting_he_cares_about_is_booked_by_his_decision_to_go() -> None:
    keen = {v: 0.05 for v in STARTING_VALUES} | {"curiosity": 0.95, "care": 0.95}
    for offset in range(60):
        history = raised_on("library-hours", date(2026, 6, 1) + timedelta(days=offset), keen)
        if any(e.kind == "schedule.created" for e in history):
            break
    else:
        raise AssertionError("He never decided to go to a meeting he cared about")
    formed = next(e for e in history if e.kind == "opinion.formed")
    planned = next(e for e in history if e.kind == "town.meeting_planned")
    intention = next(e for e in history if e.kind == "intention.adopted")
    booking = next(e for e in history if e.kind == "schedule.created")
    assert planned.causation_id == formed.event_id
    assert booking.causation_id == planned.event_id == intention.causation_id
    assert history.index(intention) < history.index(booking)
    assert booking.payload["intention_id"] == intention.payload["intention_id"]
    assert booking.payload["location_id"] == "council-office"
    starts = datetime.fromisoformat(booking.payload["starts_at"])
    assert starts.weekday() == 2 and starts.hour == 19
    raised = next(e for e in history if e.kind == "town.issue")
    assert starts.date().isoformat() == raised.payload["meeting_on"]


def test_no_booking_without_a_council_rooms() -> None:
    keen = {v: 0.05 for v in STARTING_VALUES} | {"curiosity": 0.95, "care": 0.95}
    for offset in range(60):
        history = raised_on(
            "library-hours", date(2026, 6, 1) + timedelta(days=offset), keen, venue=None
        )
        assert not any(e.kind in {"schedule.created", "town.meeting_planned"} for e in history)


def test_the_meeting_can_change_his_mind() -> None:
    changed = None
    for offset in range(200):
        history = raised_on("old-mill-flats", date(2026, 6, 1) + timedelta(days=offset))
        raised = next(e for e in history if e.kind == "town.issue")
        meeting_on = date.fromisoformat(raised.payload["meeting_on"])
        output = town_issue_events(
            history,
            at(meeting_on, REVIEW_HOUR),
            awake=True,
            values=VALUES,
            calendar={"town-meeting-old-mill-flats": "completed"},
            venue="council-office",
        )
        changed = next((e for e in output if e.kind == "opinion.changed"), None)
        if changed is not None:
            break
    assert changed is not None, "Nobody at any meeting ever moved him"
    meeting = next(e for e in output if e.kind == "town.issue")
    assert meeting.payload["stage"] == "meeting"
    assert changed.causation_id == meeting.event_id
    assert changed.payload["side"] != changed.payload["previous_side"]
    assert changed.payload["side"] == views([*history, *output])["old-mill-flats"].side
    context = town_issues_context([*history, *output], at(meeting_on, REVIEW_HOUR))
    assert "he_used_to_think" in context[0]


def test_a_meeting_he_missed_changes_nothing() -> None:
    for offset in range(40):
        history = raised_on("old-mill-flats", date(2026, 6, 1) + timedelta(days=offset))
        raised = next(e for e in history if e.kind == "town.issue")
        meeting_on = date.fromisoformat(raised.payload["meeting_on"])
        output = town_issue_events(
            history,
            at(meeting_on, REVIEW_HOUR),
            awake=True,
            values=VALUES,
            calendar={},
            venue="council-office",
        )
        assert [e.kind for e in output] == ["town.issue", "memory.recorded"]


def test_talking_it_over_with_ellis_can_change_his_mind() -> None:
    found = None
    for offset in range(200):
        start = date(2026, 6, 1) + timedelta(days=offset)
        history = raised_on("old-town-20mph", start)
        if views(history)["old-town-20mph"].side != "for":
            continue  # Ellis is against; he can only be talked out of being for it
        history = live(history, start + timedelta(days=1), 20, with_ellis=True)
        discussed = [e for e in history if e.kind == "opinion.discussed"]
        assert len(discussed) <= 1
        changed = [e for e in history if e.kind == "opinion.changed"]
        if discussed and changed and changed[0].payload["because_of"] == "Ellis":
            found = (history, discussed[0], changed[0])
            break
    assert found is not None, "Ellis never talked him round"
    history, discussed, changed = found
    assert changed.causation_id == discussed.event_id
    memory = next(
        e
        for e in history
        if e.kind == "memory.recorded" and e.payload["source_event_id"] == str(discussed.event_id)
    )
    assert memory.payload["person_id"] == "ellis"
    assert "Ellis" in memory.payload["text"]
    now = datetime.fromisoformat(changed.payload["simulated_at"])
    assert "ellis_thinks" in town_issues_context(history, now)[0]


def test_ellis_only_comes_up_at_the_workshop() -> None:
    history = raised_on("old-town-20mph", date(2026, 6, 1))
    history = live(history, date(2026, 6, 2), 20, with_ellis=False)
    assert not any(e.kind == "opinion.discussed" for e in history)


def test_the_outcome_pleases_or_disappoints_him_as_much_as_he_cared() -> None:
    seen: dict[str, float] = {}
    for offset in range(120):
        history = raised_on("library-hours", date(2026, 6, 1) + timedelta(days=offset))
        raised = next(e for e in history if e.kind == "town.issue")
        decided_on = date.fromisoformat(raised.payload["decided_on"])
        view = views(history)["library-hours"]
        output = town_issue_events(
            history,
            at(decided_on, DECISION_HOUR),
            awake=True,
            values=VALUES,
            calendar={},
            venue="council-office",
        )
        decided = next(e for e in output if e.kind == "town.issue")
        outcome = next(e for e in output if e.kind == "opinion.outcome")
        assert decided.payload["stage"] == "decided"
        assert outcome.causation_id == decided.event_id
        approved = decided.payload["outcome"] == "approved"
        expected = (
            "unbothered"
            if view.side == "torn"
            else "pleased"
            if (view.side == "for") == approved
            else "disappointed"
        )
        assert outcome.payload["feeling"] == expected
        effect = _effect(outcome, _AppraisalIndex())
        if expected != "unbothered":
            assert effect is not None
            seen[expected] = effect[2]
        after = [*history, *output]
        context = town_issues_context(after, at(decided_on, DECISION_HOUR))
        assert context[0]["where_it_stands"].startswith("decided: ")
        assert town_issues_context(after, at(decided_on, DECISION_HOUR) + timedelta(days=200)) == []
        if len(seen) == 2:
            break
    assert seen["pleased"] > 0 > seen["disappointed"]


def test_asked_about_the_town_he_gives_his_view() -> None:
    history = raised_on("twelve-bus", date(2026, 6, 3))
    context = {
        "identity": {
            "selfhood": {
                "views_on_the_town": town_issues_context(history, at(date(2026, 6, 3), 14))
            }
        }
    }
    view = views(history)["twelve-bus"]
    words = {"for": BY_ID["twelve-bus"].words_for, "against": BY_ID["twelve-bus"].words_against}
    reply = _standin_town_reply("what's going on with the council?", context)
    assert reply is not None and words.get(view.side, BY_ID["twelve-bus"].words_torn) in reply
    assert _standin_town_reply("what do you think about the bus?", context) == reply
    assert _standin_town_reply("how was your day?", context) is None
    assert _standin_town_reply("any news from the council?", {}) is not None
