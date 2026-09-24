"""An evening class: ten Tuesdays of something he cares about, finished or not.

In September the community hall's autumn classes go up on the noticeboard, and some years
one of them is exactly him. He signs up, pays the fee, and goes on Tuesday evenings, among
people he wouldn't otherwise meet. Whether he sees it through is his own doing: most
weeks he goes; some weeks he's tired and doesn't. If he makes seven of the ten he finishes
with something he made and a quiet pride; if not, it becomes one more thing he started and
didn't finish, which he notices.

Which class depends on who he is: craft pulls toward furniture restoration, curiosity
toward local history, and, if he has come to love drawing, life drawing. He takes one
at most every other year, and only if the fee won't leave him short. Most weeks he goes;
on a Tuesday when he's worn out or low he may skip it.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

KIND = "course.stage"
SESSIONS = 10
FINISHES_WITH = 7
ENROL_CHANCE = 0.6
SETTLED_FOR = timedelta(days=240)
AGAIN_AFTER = timedelta(days=700)
FEE_PENCE = 12_000

# value that pulls toward it -> (course, title, how it went)
COURSES = {
    "craft": (
        "furniture-restoration",
        "Furniture restoration for beginners",
        "I've got a chair I'll actually be proud of. Three coats of wax and a joint that "
        "doesn't wobble.",
    ),
    "curiosity": (
        "local-history",
        "Alderwick through the centuries",
        "I know why Mill Street bends now, and who the churchyard's angel was for. I keep "
        "telling people. They're very patient.",
    ),
    "drawing": (
        "life-drawing",
        "Life drawing, beginners welcome",
        "My last drawing was nearly good. The tutor said I've stopped drawing what I think "
        "things look like, which apparently is the whole trick.",
    ),
}


def evening_course_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    values: Mapping[str, float],
    balance_pence: int,
    rent_pence: int,
    calendar: Mapping[str, str],
    venue: str,
    loves_drawing: bool = False,
    worn_out: bool = False,
) -> list[DomainEvent]:
    """Sign up in September, skip a Tuesday now and then, and finish or admit he stopped."""
    if not awake:
        return []
    stages = events_of(history, KIND)
    latest = stages[-1] if stages else None
    if latest is not None and latest.payload.get("stage") == "enrolled":
        return _skip_tonight(latest, at, calendar, worn_out) or _end_of_course(latest, at, calendar)
    if at.month != 9 or at.weekday() != 6 or at.day > 7 or at.hour != 19:
        return []
    opened = events_of(history, "finance.account_opened")
    if not opened or at - _time(opened[0]) < SETTLED_FOR:
        return []
    if latest is not None and at - _time(latest) < AGAIN_AFTER:
        return []
    if balance_pence < FEE_PENCE + rent_pence + 3_000:
        return []
    if _roll("enrol", at.year) >= ENROL_CHANCE:
        return []
    pulls = {
        "craft": float(values.get("craft", 0.72)),
        "curiosity": 0.8 * float(values.get("curiosity", 0.84)),
        **({"drawing": 0.9} if loves_drawing else {}),
    }
    pick = _roll("which", at.year) * sum(pulls.values())
    for value, pull in pulls.items():
        pick -= pull
        if pick <= 0:
            break
    course_id, title, _ = COURSES[value]
    return _enrol(course_id, title, "craft" if value == "drawing" else value, at, venue)


def _skip_tonight(
    enrolled: DomainEvent, at: datetime, calendar: Mapping[str, str], worn_out: bool
) -> list[DomainEvent]:
    """An hour before class, on a bad day, he might not go."""
    if at.hour != 18 or at.weekday() != 1:
        return []
    run_id = str(enrolled.payload["course_run_id"])
    first = date.fromisoformat(str(enrolled.payload["first_session"]))
    week = (at.date() - first).days // 7 + 1
    schedule_id = f"{run_id}-week-{week}"
    if not 1 <= week <= SESSIONS or calendar.get(schedule_id) != "scheduled":
        return []
    chance = 0.08 + (0.35 if worn_out else 0.0)
    if _roll("skip", schedule_id) >= chance:
        return []
    cancelled = DomainEvent(
        "schedule.cancelled",
        "pathos",
        {
            "schedule_id": schedule_id,
            "reason": "Too worn out; skipped the class this week.",
            "simulated_at": at.isoformat(),
        },
        causation_id=enrolled.event_id,
        correlation_id=schedule_id,
    )
    abandoned = DomainEvent(
        "intention.abandoned",
        "pathos",
        {
            "intention_id": f"{schedule_id}-intention",
            "reason": "Skipped the class this week.",
            "simulated_at": at.isoformat(),
        },
        causation_id=cancelled.event_id,
        correlation_id=schedule_id,
    )
    return [cancelled, abandoned]


def _first_tuesday_after(day: date) -> date:
    return day + timedelta(days=(1 - day.weekday()) % 7 or 7)


def _enrol(course_id: str, title: str, value: str, at: datetime, venue: str) -> list[DomainEvent]:
    run_id = f"{course_id}-{at.year}"
    first = _first_tuesday_after(at.date() + timedelta(days=7))
    text = (
        f"Signed up for an evening class at the community hall: '{title}'. Ten Tuesdays. "
        "Paid before I could find a reason not to."
    )
    enrolled = DomainEvent(
        KIND,
        "pathos",
        {
            "course_run_id": run_id,
            "course_id": course_id,
            "stage": "enrolled",
            "title": title,
            "value_id": value,
            "fee_pence": FEE_PENCE,
            "first_session": first.isoformat(),
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=run_id,
    )
    output = [enrolled, _memory(enrolled, text, at, 0.55)]
    for week in range(SESSIONS):
        day = first + timedelta(days=7 * week)
        starts = datetime(day.year, day.month, day.day, 19, tzinfo=at.tzinfo)
        schedule_id = f"{run_id}-week-{week + 1}"
        intention_id = f"{schedule_id}-intention"
        output += [
            DomainEvent(
                "intention.adopted",
                "pathos",
                {
                    "proposal_id": schedule_id,
                    "intention_id": intention_id,
                    "actor_id": "pathos",
                    "action": "learn",
                    "target_id": venue,
                    "goal_id": None,
                    "priority": 0.7,
                    "motivation": f"{title}, week {week + 1}.",
                    "simulated_at": at.isoformat(),
                },
                causation_id=enrolled.event_id,
                correlation_id=schedule_id,
            ),
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": schedule_id,
                    "intention_id": intention_id,
                    "title": f"{title} (week {week + 1})",
                    "starts_at": starts.isoformat(),
                    "ends_at": (starts + timedelta(hours=2)).isoformat(),
                    "location_id": venue,
                    "actor_id": "pathos",
                    "action": "learn",
                    "target_id": venue,
                    "resource_id": None,
                    "companion_id": None,
                    "activity_type": "an_evening_class",
                    "source": "evening_course",
                    "simulated_at": at.isoformat(),
                },
                causation_id=enrolled.event_id,
                correlation_id=schedule_id,
            ),
        ]
    return output


def _end_of_course(
    enrolled: DomainEvent, at: datetime, calendar: Mapping[str, str]
) -> list[DomainEvent]:
    first = date.fromisoformat(str(enrolled.payload["first_session"]))
    last = first + timedelta(days=7 * (SESSIONS - 1))
    if at.date() != last + timedelta(days=1) or at.hour != 19:
        return []
    run_id = str(enrolled.payload["course_run_id"])
    attended = sum(
        1 for week in range(SESSIONS) if calendar.get(f"{run_id}-week-{week + 1}") == "completed"
    )
    course_id = str(enrolled.payload["course_id"])
    finished = attended >= FINISHES_WITH
    outcome = next(text for cid, _, text in COURSES.values() if cid == course_id)
    text = (
        f"Last night was the last class. Went to {attended} of ten. {outcome}"
        if finished
        else f"The class finished last night. I stopped going after a few weeks; made {attended} "
        "of ten. Another thing I started and didn't finish. I'd like to stop doing that."
    )
    stage = DomainEvent(
        KIND,
        "pathos",
        {
            "course_run_id": run_id,
            "course_id": course_id,
            "stage": "finished" if finished else "dropped",
            "attended": attended,
            "value_id": enrolled.payload.get("value_id"),
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        causation_id=enrolled.event_id,
        correlation_id=run_id,
    )
    return [stage, _memory(stage, text, at, 0.7 if finished else 0.5)]


def course_context(history: Sequence[DomainEvent]) -> dict[str, object] | None:
    stages = events_of(history, KIND)
    if not stages:
        return None
    latest = stages[-1]
    return {
        "course": next(
            (
                str(e.payload["title"])
                for e in reversed(stages)
                if e.payload.get("course_run_id") == latest.payload.get("course_run_id")
                and e.payload.get("title")
            ),
            None,
        ),
        "status": {
            "enrolled": "doing it now, Tuesday evenings",
            "finished": "finished it",
            "dropped": "stopped going",
        }.get(str(latest.payload.get("stage"))),
        "how_it_went": str(latest.payload["text"]),
    }


def course_fee(history: Sequence[DomainEvent], at: datetime) -> list[tuple[str, int, str]]:
    output: list[tuple[str, int, str]] = []
    for event in reversed(events_of(history, KIND)):
        if at - _time(event) > timedelta(days=2):
            break
        if event.payload.get("stage") == "enrolled":
            output.append(
                (
                    f"course-{event.payload['course_run_id']}",
                    int(event.payload["fee_pence"]),
                    f"Course fee: {event.payload['title']}",
                )
            )
    return output


def _memory(source: DomainEvent, text: str, at: datetime, importance: float) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "milestone",
            "source": "lived-course",
            "source_event_id": str(source.event_id),
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )


def _time(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
