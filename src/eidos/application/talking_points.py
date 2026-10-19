"""What two people actually have to talk about, and why they're both there.

Given only a label ("following up with ellis"), a model talking for them filled the gap
with invented arcs ("something from my past… it's not a burden anymore") on the very
morning he told Ellis he was leaving. Rules choose the true, shared things in front of
them (his news, the job on the bench, a plan they've both said yes to, something one of
them has heard, the weather); the model only says it.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from eidos.application.freelance import DROP_IN_PREFIX, STARTED, TOLD, leaving_day
from eidos.application.gossip import worth_mentioning
from eidos.application.life_context import latest_weather
from eidos.application.repair_jobs import bench_view
from eidos.application.town_story import both_know
from eidos.application.work_rota import EMPLOYER_ID
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.planning import project_planning


def talking_points(
    history: Sequence[DomainEvent],
    at: datetime,
    partner_id: str,
    partner_name: str,
    location_id: str,
) -> list[tuple[str, str]]:
    """(topic id, what it is in words) for this pair here and now, most pressing first."""
    points: list[tuple[str, str]] = []
    told = events_of(history, TOLD)
    if told and not events_of(history, STARTED):
        when = datetime.fromisoformat(str(told[0].payload["simulated_at"]))
        last = leaving_day(history)
        try:
            last_words = datetime.fromisoformat(last).strftime("%A %-d %B")
        except ValueError:
            last_words = "soon"
        if partner_id == EMPLOYER_ID and at - when <= timedelta(days=10):
            points.append(
                (
                    "leaving-the-workshop",
                    "Patrick leaving the workshop to go freelance as a writer, which he's told "
                    f"{partner_name} about; his last shift is {last_words}",
                )
            )
        elif at - when <= timedelta(days=14):
            points.append(
                (
                    "going-freelance",
                    "Patrick going freelance as a writer and leaving the repair workshop "
                    "(his own news, his to tell)",
                )
            )
    if location_id == "workshop":
        for index, line in enumerate(bench_view(history, at)[:2]):
            points.append((f"on-the-bench-{index}", f"the job on the bench: {line}"))
    planning = project_planning(history)
    for entry in sorted(planning.calendar.values(), key=lambda e: e.starts_at):
        if entry.companion_id != partner_id or entry.status != "scheduled":
            continue
        starts = datetime.fromisoformat(entry.starts_at)
        if timedelta(0) < starts - at <= timedelta(days=7):
            points.append(
                (
                    f"plan-{entry.schedule_id}",
                    f"{entry.title} together, {starts:%A} (a plan they've both agreed to)",
                )
            )
            break
    for claim_id, text in both_know(history, at, partner_id):
        points.append((claim_id, f"what's happened in town, which they've both heard: {text}"))
    heard = worth_mentioning(history, partner_id, at)
    if heard is not None:
        points.append(
            (f"heard-{heard.claim_id}", f"something {partner_name} has heard: {heard.text}")
        )
    for index, project in enumerate(his_projects(history)[:1]):
        points.append((f"his-project-{index}", project))
    weather = latest_weather(list(history[-400:]))
    if weather:
        points.append(("the-weather", f"the weather today ({weather.lower()})"))
    return points


def his_projects(history: Sequence[DomainEvent]) -> list[str]:
    """His own projects on the go (an atlas of town sounds), which people may ask about."""
    return [
        f"Patrick's own project (his, nobody else's): {goal.title}"
        for goal in project_planning(history).goals.values()
        if goal.status == "active" and goal.goal_id.startswith("pathos-project-")
    ][:2]


def setting(
    history: Sequence[DomainEvent], at: datetime, place_name: str, partner_name: str
) -> str:
    """Why Patrick is where he is, so he doesn't 'drop in' to his own shift."""
    planning = project_planning(history)
    for entry in planning.calendar.values():
        if entry.actor_id not in {None, "pathos"} or entry.status not in {"scheduled", "active"}:
            continue
        starts = datetime.fromisoformat(entry.starts_at)
        ends = datetime.fromisoformat(entry.ends_at) if entry.ends_at else starts
        if starts <= at < ends:
            if entry.schedule_id.startswith("work-rota-"):
                return f"Patrick is at work, on his shift at the bench alongside {partner_name}"
            if entry.schedule_id.startswith(DROP_IN_PREFIX):
                return (
                    "Patrick has dropped in at Ellis's repair workshop to give Ellis a hand at "
                    "the bench. It's Ellis's workshop and Ellis runs it; Patrick used to work "
                    "there and is a freelance writer now, visiting as a friend"
                )
            return f"Patrick is at {place_name} for this: {entry.title}"
    if place_name.casefold().endswith("workshop") and events_of(history, STARTED):
        return "Patrick is visiting Ellis's repair workshop, where he used to work; it's Ellis's"
    return f"Patrick is at {place_name}"
