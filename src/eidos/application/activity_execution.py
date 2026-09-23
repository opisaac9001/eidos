"""Evidence of doing an accepted activity, separate from its calendar reservation.

No completion is inferred from a booking. Work starts when observed eligible and
only eligible elapsed intervals count. These records are not new commitments.
"""

from bisect import bisect_right
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Callable, NamedTuple, Sequence

from eidos.application.activity_stages import stage_context, stage_events
from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, events_of, events_with_prefix
from eidos.domain.planning import CalendarEntry, PlanningState

EXECUTABLE = frozenset({"work", "learn", "attend", "repair"})
FINISH_OFF_SHARE = 0.8  # A lunch hour inside a six-hour shift still completes it.


def duration_requirement(
    history: Sequence[DomainEvent], entry: CalendarEntry
) -> tuple[float, float, float]:
    """Return estimated seconds, hidden actual effort, and stated confidence.

    Only newly generated schedules that explicitly record uncertainty vary. Old,
    authored and imported schedules retain their exact historical duration.
    """
    start = datetime.fromisoformat(entry.starts_at)
    end = datetime.fromisoformat(entry.ends_at or entry.starts_at)
    planned = max(0.0, (end - start).total_seconds())
    source = next(
        (
            event
            for event in reversed(events_of(history, "schedule.created"))
            if event.payload.get("schedule_id") == entry.schedule_id
            and "estimate_confidence" in event.payload
        ),
        None,
    )
    if source is None or entry.action == "attend":
        return planned, planned, 1.0
    raw_estimate = source.payload.get("estimated_duration_seconds", planned)
    raw_confidence = source.payload.get("estimate_confidence", 1.0)
    if (
        isinstance(raw_estimate, bool)
        or not isinstance(raw_estimate, (int, float))
        or raw_estimate <= 0
        or isinstance(raw_confidence, bool)
        or not isinstance(raw_confidence, (int, float))
        or not 0 <= raw_confidence <= 1
    ):
        return planned, planned, 1.0
    estimate, confidence = float(raw_estimate), float(raw_confidence)
    sample = int.from_bytes(sha256(f"duration:{entry.schedule_id}".encode()).digest()[:4], "big")
    centered = sample / 0xFFFFFFFF * 2 - 1
    # Confidence belongs to Patrick's estimate, not to the world. Even complete
    # subjective certainty leaves ordinary work with a small chance of being wrong.
    uncertainty = 0.08 + (1 - confidence) * 0.32
    actual = max(60.0, estimate * (1 + centered * uncertainty))
    return estimate, actual, confidence


class _Timeline(NamedTuple):
    """History ordered by simulated time; events without a time inherit the clock.

    ``keys``/``entries`` are append-only lists shared between successive states, each of
    which reads only its first ``size`` items. Appending in time order (the common case)
    extends the shared list in place; a state whose lists have already grown past it (a
    divergent branch) or an out-of-order event copies first. Old states stay valid.
    """

    seen: int
    clock: datetime | None
    size: int
    keys: list[tuple[datetime, int]]
    entries: list[tuple[datetime, int, DomainEvent]]


def _timeline_folder(
    keep: Callable[[DomainEvent], bool],
) -> Callable[[_Timeline, DomainEvent], _Timeline]:
    def step(timeline: _Timeline, event: DomainEvent) -> _Timeline:
        index = timeline.seen
        raw = event.payload.get("simulated_at")
        at: datetime | None
        try:
            at = (
                timeline.clock
                if raw is None
                else raw
                if isinstance(raw, datetime)
                else datetime.fromisoformat(str(raw))
            )
        except ValueError:
            return timeline._replace(seen=index + 1)
        if at is None or at.utcoffset() is None:
            return timeline._replace(seen=index + 1)
        clock = at if event.kind == "time.advanced" else timeline.clock
        if not keep(event):
            return timeline._replace(seen=index + 1, clock=clock)
        key = (at, index)
        size = timeline.size
        keys, entries = timeline.keys, timeline.entries
        if size and key < keys[size - 1]:
            position = bisect_right(keys, key, 0, size)
            keys = [*keys[:position], key, *keys[position:size]]
            entries = [*entries[:position], (at, index, event), *entries[position:size]]
        else:
            if len(keys) != size:
                keys, entries = keys[:size], entries[:size]
            keys.append(key)
            entries.append((at, index, event))
        return _Timeline(index + 1, clock, size + 1, keys, entries)

    return step


_TIMELINE_FOLD: IncrementalFold[_Timeline] = IncrementalFold(
    lambda: _Timeline(0, None, 0, [], []), _timeline_folder(lambda _event: True), capacity=8
)

# activity_effort only changes state at these events; skipping the rest cannot change the
# total, because eligibility is constant between them and elapsed time is summed piecewise.
_EFFORT_KINDS = frozenset(
    {
        "pathos.travel_started",
        "pathos.moved",
        "schedule.interrupted",
        "schedule.cancelled",
        "schedule.failed",
        "schedule.completed",
        "schedule.rescheduled",
        "sleep.started",
        "sleep.ended",
        "incident.response_started",
        "incident.response_completed",
        "incident.response_abandoned",
        "phone.call_answered",
        "phone.call_completed",
        "scene.started",
        "scene.ended",
        "scene.interrupted",
        "scene.resumed",
        "npc.moved",
        "npc.travel_started",
        "activity.execution_started",
        "activity.execution_paused",
        "activity.execution_resumed",
    }
)
_EFFORT_FOLD: IncrementalFold[_Timeline] = IncrementalFold(
    lambda: _Timeline(0, None, 0, [], []),
    _timeline_folder(lambda event: event.kind in _EFFORT_KINDS or event.kind.startswith("object.")),
    capacity=8,
)


def _visible(timeline: _Timeline, now: datetime) -> list[tuple[datetime, int, DomainEvent]]:
    visible = bisect_right(timeline.keys, (now, timeline.seen), 0, timeline.size)
    return timeline.entries[:visible]


def _timeline(
    history: Sequence[DomainEvent], now: datetime
) -> list[tuple[datetime, int, DomainEvent]]:
    return _visible(_TIMELINE_FOLD(history), now)


def activity_effort(
    history: Sequence[DomainEvent], entry: CalendarEntry, now: datetime
) -> dict[str, object]:
    """Replay actual presence, sleep and conversations; never count paused time."""
    if now.utcoffset() is None:
        raise ValueError("Activity execution requires timezone-aware time")
    end = datetime.fromisoformat(entry.ends_at or entry.starts_at)
    start = datetime.fromisoformat(entry.starts_at)
    starts = [
        e
        for e in events_of(history, "activity.execution_started")
        if e.payload.get("schedule_id") == entry.schedule_id
    ]
    first = starts[0] if starts else None
    required = (
        float(first.payload["required_seconds"])
        if first
        else max(0.0, (end - start).total_seconds())
    )
    estimated = float(first.payload.get("estimated_seconds", required)) if first else required
    estimate_confidence = float(first.payload.get("estimate_confidence", 1.0)) if first else 1.0
    window_start, window_end = start, end
    if first and first.payload.get("window_starts_at"):
        window_start = datetime.fromisoformat(str(first.payload["window_starts_at"]))
        window_end = datetime.fromisoformat(str(first.payload["window_ends_at"]))
    location, awake = "home", False
    scenes: dict[str, bool] = {}
    companion_location = None
    occupied: set[str] = set()
    running = False
    cursor = window_start
    worked = 0.0
    began = None
    resource: dict[str, object] | None = None
    resource_id = entry.target_id if entry.action == "repair" else entry.resource_id

    def reason() -> str | None:
        if not awake:
            return "asleep"
        if location != entry.location_id:
            return "elsewhere"
        if resource_id and (
            resource is None
            or resource.get("location_id") != location
            or resource.get("custodian_id") not in {"pathos", "community"}
            or resource.get("quantity") == 0
            or (entry.action != "repair" and resource.get("condition") == "broken")
            or (entry.action == "repair" and resource.get("condition") != "broken")
        ):
            return "resource_unavailable"
        if any(scenes.values()):
            return "conversation"
        if occupied:
            return "interruption"
        if entry.companion_id and companion_location != entry.location_id:
            return "companion_absent"
        return None

    for at, _, event in _visible(_EFFORT_FOLD(history), now):
        boundary = min(at, window_end)
        if running and boundary > cursor and reason() is None:
            worked += (boundary - cursor).total_seconds()
        cursor = max(cursor, boundary)
        p = event.payload
        if event.aggregate_id != "pathos":
            continue
        if event.kind == "pathos.travel_started":
            location = "in_transit"
        elif event.kind == "pathos.moved":
            location = str(p["location_id"])
        elif resource_id and p.get("object_id") == resource_id and event.kind.startswith("object."):
            if event.kind == "object.registered":
                resource = dict(p)
            elif resource is not None:
                resource.update(
                    {
                        key: p[key]
                        for key in ("location_id", "custodian_id", "quantity", "condition")
                        if key in p
                    }
                )
        elif p.get("schedule_id") == entry.schedule_id and event.kind in {
            "schedule.interrupted",
            "schedule.cancelled",
            "schedule.failed",
            "schedule.completed",
        }:
            running = False
        elif p.get("schedule_id") == entry.schedule_id and event.kind == "schedule.rescheduled":
            window_start = datetime.fromisoformat(str(p["starts_at"]))
            window_end = datetime.fromisoformat(str(p["ends_at"]))
            cursor = max(at, window_start)
            running = False
        elif event.kind == "sleep.started":
            awake = False
        elif event.kind == "sleep.ended":
            awake = True
        elif event.kind == "incident.response_started":
            occupied.add(str(p.get("incident_id")))
        elif event.kind == "phone.call_answered":
            occupied.add(f"phone:{p['call_id']}")
        elif event.kind == "phone.call_completed":
            occupied.discard(f"phone:{p['call_id']}")
        elif event.kind in {"incident.response_completed", "incident.response_abandoned"}:
            occupied.discard(str(p.get("incident_id")))
        elif event.kind == "scene.started" and "pathos" in {
            p.get("initiator_id"),
            p.get("partner_id"),
        }:
            scenes[str(p["scene_id"])] = True
        elif event.kind in {"scene.ended", "scene.interrupted", "scene.resumed"}:
            if str(p.get("scene_id")) in scenes:
                scenes[str(p["scene_id"])] = event.kind == "scene.resumed"
        elif p.get("actor_id") == entry.companion_id and entry.companion_id:
            if event.kind == "npc.moved":
                companion_location = p.get("location_id")
            elif event.kind == "npc.travel_started":
                companion_location = None
        elif (
            event.kind == "activity.execution_started" and p.get("schedule_id") == entry.schedule_id
        ):
            running = True
            began = at.isoformat()
            cursor = max(window_start, at)
        elif (
            event.kind in {"activity.execution_paused", "activity.execution_resumed"}
            and p.get("schedule_id") == entry.schedule_id
        ):
            running = event.kind == "activity.execution_resumed"
            cursor = max(cursor, window_start, at)
            if running and p.get("resume_after"):
                cursor = max(cursor, datetime.fromisoformat(str(p["resume_after"])))
    boundary = min(now, window_end)
    if running and boundary > cursor and reason() is None:
        worked += (boundary - cursor).total_seconds()
    return {
        "schedule_id": entry.schedule_id,
        "title": entry.title,
        "started_at": began,
        "worked_seconds": min(required, worked),
        "required_seconds": required,
        "estimated_seconds": estimated,
        "estimate_confidence": estimate_confidence,
        "remaining_seconds": max(0.0, required - worked),
        "blocked_by": reason(),
        # Nearly there when the reserved time runs out, he stays the few extra minutes.
        "ready": began is not None
        and (
            worked + 0.001 >= required
            or (now >= window_end and worked >= FINISH_OFF_SHARE * required and reason() is None)
        ),
        "window_ended": now >= end,
        "is_working": running
        and reason() is None
        and window_start <= now < window_end
        and worked < required,
        "action_authority": False,
        "window_starts_at": start.isoformat(),
        "window_ends_at": end.isoformat(),
    }


def execution_events(
    history: Sequence[DomainEvent], planning: PlanningState, now: datetime
) -> list[DomainEvent]:
    """Start at the observed instant; record interruptions and durable unfinished work."""
    output: list[DomainEvent] = []
    # The planning resolver normally prevents overlaps. Keep execution single-focus
    # even for imported conflicting reservations.
    claimed = False
    for entry in sorted(
        planning.calendar.values(),
        key=lambda e: (e.commitment_id is None, e.starts_at, e.schedule_id),
    ):
        if entry.actor_id not in {None, "pathos"} or entry.action not in EXECUTABLE:
            continue
        if entry.status != "scheduled" or now < datetime.fromisoformat(entry.starts_at):
            continue
        effort = activity_effort(history, entry, now)
        output.extend(stage_events([*history, *output], entry, effort, now))
        own = [
            e
            for e in events_with_prefix(history, "activity.execution_")
            if e.payload.get("schedule_id") == entry.schedule_id
        ]
        if effort["window_ended"]:
            kind = "ready" if effort["ready"] else "unfinished"
        elif effort["blocked_by"] is not None or claimed:
            if effort["started_at"] is None:
                continue
            kind = "paused"
        else:
            claimed = True
            kind = "started" if effort["started_at"] is None else "resumed"
        resume_after = None
        if kind == "resumed" and own and own[-1].kind == "activity.execution_paused":
            pause = own[-1]
            cues = {
                "scene.ended",
                "scene.interrupted",
                "incident.response_completed",
                "incident.response_abandoned",
                "sleep.ended",
                "thought.recorded",
                "needs.changed",
                "affect.changed",
                "object.custody_changed",
                "phone.call_completed",
            }
            cause = next(
                (e for _, _, e in reversed(_timeline(history, now)) if e.kind in cues), pause
            )
            decisions = [
                e
                for e in events_of(history, "activity.resumption_decided")
                if e.payload.get("pause_id") == str(pause.event_id)
            ]
            if decisions and decisions[-1].payload.get("source_event_id") == str(cause.event_id):
                claimed = False
                continue
            energy = next(
                (
                    float(e.payload["energy"])
                    for _, _, e in reversed(_timeline(history, now))
                    if e.kind == "affect.changed" and "energy" in e.payload
                ),
                1.0,
            )
            intention = planning.intentions.get(entry.intention_id or "")
            priority = intention.priority if intention else 0.5
            resume = energy >= 0.25 or priority >= 0.8
            pause_reason = str(pause.payload.get("reason") or "interruption")
            switching_rate = {
                "conversation": 0.1,
                "interruption": 0.2,
                "asleep": 0.05,
                "elsewhere": 0.08,
                "resource_unavailable": 0.05,
            }.get(pause_reason, 0.12)
            duration = (
                now - datetime.fromisoformat(str(pause.payload["simulated_at"]))
            ).total_seconds()
            cost = min(120.0, max(0.0, duration * switching_rate))
            window_end = datetime.fromisoformat(str(effort["window_ends_at"]))
            available = max(0.0, (window_end - now).total_seconds() - cost)
            cannot_finish = float(str(effort["remaining_seconds"])) > available + 0.001
            decision_name = (
                "shorten"
                if resume
                and cannot_finish
                and entry.commitment_id is None
                and entry.goal_id is None
                and priority < 0.8
                else "resume"
                if resume
                else "defer"
            )
            decision = DomainEvent(
                "activity.resumption_decided",
                "pathos",
                {
                    "schedule_id": entry.schedule_id,
                    "pause_id": str(pause.event_id),
                    "source_event_id": str(cause.event_id),
                    "decision": decision_name,
                    "reason": "He chose a smaller stopping point rather than pretending the whole task would fit."
                    if decision_name == "shorten"
                    else "The intention still mattered and he had enough energy to return."
                    if decision_name == "resume"
                    else "He did not have the energy to settle back into this task.",
                    "switching_cost_seconds": cost,
                    "available_work_seconds": available,
                    "remaining_work_seconds": effort["remaining_seconds"],
                    "simulated_at": now.isoformat(),
                    "action_authority": False,
                },
                causation_id=cause.event_id,
                correlation_id=entry.schedule_id,
            )
            output.append(decision)
            if not resume:
                claimed = False
                continue
            if decision_name == "shorten":
                output.append(
                    DomainEvent(
                        "activity.scope_shortened",
                        "pathos",
                        {
                            "schedule_id": entry.schedule_id,
                            "pause_id": str(pause.event_id),
                            "available_work_seconds": available,
                            "remaining_work_seconds": effort["remaining_seconds"],
                            "meaning": "Only the remaining session was shortened; unfinished work is not completion.",
                            "simulated_at": now.isoformat(),
                            "action_authority": False,
                        },
                        causation_id=decision.event_id,
                        correlation_id=entry.schedule_id,
                    )
                )
            # Recovering the thread consumes actual time; never extend the booking.
            resume_after = (now + timedelta(seconds=cost)).isoformat()
        if (
            own
            and own[-1].payload.get("window_starts_at", entry.starts_at) == entry.starts_at
            and (
                own[-1].kind == f"activity.execution_{kind}"
                or kind == "resumed"
                and own[-1].kind == "activity.execution_started"
            )
        ):
            continue
        duration_payload: dict[str, object] = {}
        if kind == "started":
            estimated, required, confidence = duration_requirement(history, entry)
            duration_payload = {
                "estimated_seconds": estimated,
                "required_seconds": required,
                "remaining_seconds": required,
                "estimate_confidence": confidence,
                "duration_outcome_hidden_from_pathos": abs(required - estimated) > 0.001,
            }
        output.append(
            DomainEvent(
                f"activity.execution_{kind}",
                "pathos",
                {
                    **effort,
                    "owner": "pathos",
                    "staged_execution": True,
                    "resume_after": resume_after,
                    **duration_payload,
                    "reason": "competing_activity"
                    if claimed and kind == "paused"
                    else effort["blocked_by"],
                    "simulated_at": now.isoformat(),
                },
                causation_id=own[-1].event_id if own else None,
                correlation_id=entry.schedule_id,
            )
        )
    return output


def execution_context(
    history: Sequence[DomainEvent],
    planning: PlanningState,
    now: datetime,
    *,
    observer: bool = False,
) -> list[dict[str, object]]:
    """Personal action evidence, not private world-director facts or perfect memories."""
    ids = {e.payload.get("schedule_id") for e in events_with_prefix(history, "activity.execution_")}
    staged_ids = {
        e.payload.get("schedule_id")
        for e in events_of(history, "activity.execution_started")
        if e.payload.get("staged_execution")
    }
    records = []
    for entry in [e for e in planning.calendar.values() if e.schedule_id in ids][-8:]:
        effort = activity_effort(history, entry, now)
        records.append(
            effort
            | {
                "schedule_status": entry.status,
                "stages": stage_context(entry, effort) if entry.schedule_id in staged_ids else [],
            }
        )
    if observer:
        return records
    # Exact effort counters belong to inspection, not to an infallible personal
    # memory. Only present/recent activity is supplied directly to performers.
    recent = {
        e.payload.get("schedule_id")
        for at, _, e in _timeline(history, now)
        if e.kind.startswith("activity.execution_") and (now - at).total_seconds() <= 3600
    }
    output = []
    for item in records:
        if item["schedule_status"] != "scheduled" and item["schedule_id"] not in recent:
            continue
        required = float(str(item["required_seconds"]))
        proportion = float(str(item["worked_seconds"])) / max(1, required)
        stages = item["stages"] if isinstance(item["stages"], list) else []
        output.append(
            {
                "title": item["title"],
                "has_started": item["started_at"] is not None and proportion > 0,
                "schedule_status": item["schedule_status"],
                "outcome": "completed"
                if item["schedule_status"] == "completed"
                else "not completed",
                "effort": "the intended session"
                if proportion >= 1
                else "most of the intended time"
                if proportion >= 0.75
                else "some time"
                if proportion >= 0.25
                else "a little time"
                if proportion > 0
                else "no time yet",
                "present_situation": "I am working on this now."
                if item["is_working"] and item["schedule_status"] == "scheduled"
                else "This session is complete."
                if item["schedule_status"] == "completed"
                else "I am not working on this at this moment.",
                "duration_expectation": "I am not very sure how long this will take."
                if float(str(item["estimate_confidence"])) < 0.4
                else "The time estimate is only approximate."
                if float(str(item["estimate_confidence"])) < 0.8
                else "I have a fairly firm sense of the time this needs.",
                "interruption": item["blocked_by"] if not item["window_ended"] else None,
                "unfinished": bool(item["window_ended"] and not item["ready"]),
                "current_stage": next(
                    (stage["label"] for stage in stages if stage["status"] != "completed"),
                    None,
                ),
                "completed_stages": [
                    stage["label"] for stage in stages if stage["status"] == "completed"
                ],
                "action_authority": False,
                "meaning": "This recent activity was actually completed and its outcome validated."
                if item["schedule_status"] == "completed"
                else "This activity has NOT been completed. Stages may be partly done; effort is not success. This is current/recent context, not a permanent perfect memory.",
            }
        )
    return output


def execution_window_events(
    history: Sequence[DomainEvent], planning: PlanningState, since: datetime, now: datetime
) -> list[DomainEvent]:
    """Evaluate accepted start/end boundaries without running hourly body/model loops."""
    points = {since, now}
    for at, _, event in _timeline(history, now):
        if since <= at and event.kind in {
            "pathos.travel_started",
            "pathos.moved",
            "sleep.ended",
            "scene.ended",
            "scene.started",
            "scene.interrupted",
            "scene.resumed",
            "incident.response_started",
            "incident.response_completed",
            "incident.response_abandoned",
        }:
            points.add(at)
    for entry in planning.calendar.values():
        if entry.status != "scheduled" or entry.action not in EXECUTABLE:
            continue
        for raw in (entry.starts_at, entry.ends_at):
            if raw:
                at = datetime.fromisoformat(raw)
                if since <= at <= now:
                    points.add(at)
    output: list[DomainEvent] = []
    for at in sorted(points):
        output.extend(execution_events([*history, *output], planning, at))
    return output
