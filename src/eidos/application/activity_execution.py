"""Evidence of doing an accepted activity, separate from its calendar reservation.

No completion is inferred from a booking. Work starts when observed eligible and
only eligible elapsed intervals count. These records are not new commitments.
"""

from bisect import bisect_left, bisect_right
from collections import OrderedDict
from datetime import datetime, timedelta
from hashlib import sha256
from threading import Lock
from typing import Callable, NamedTuple, Sequence

from eidos.application.activity_stages import stage_context, stage_events
from eidos.application.work_rota import EMPLOYER_ID, ROTA_PREFIX
from eidos.domain.events import DomainEvent
from eidos.domain.folding import (
    CombinedEvents,
    EventView,
    IncrementalFold,
    events_of,
    events_with_prefix,
)
from eidos.domain.planning import CalendarEntry, PlanningState

EXECUTABLE = frozenset({"work", "learn", "attend", "repair"})
# Stays, where the point is being there rather than effort put in.
STAYS = frozenset({"christmas_at_home", "visiting_home"})
# Activities that are sociable by nature: a conversation at the venue is part of them.
SOCIABLE = frozenset(
    {"an_evening_out", "an_evening_class", "visiting_home", "christmas_at_home", "moving_house"}
)
_HERE = "*anyone-here*"
FINISH_OFF_SHARE = 0.8  # A lunch hour inside a six-hour shift still completes it.
LONG_STINT_SECONDS = 3 * 3600


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

    ``keys``/``entries``/``events`` are append-only lists shared between successive states,
    each of which reads only its first ``size`` items; ``events`` holds each entry's event.
    Appending in time order (the common case) extends the shared lists in place; a state
    whose lists have already grown past it (a divergent branch) or an out-of-order event
    copies first. Old states stay valid, and a list's items never change once written.
    """

    seen: int
    clock: datetime | None
    size: int
    keys: list[tuple[datetime, int]]
    entries: list[tuple[datetime, int, DomainEvent]]
    events: list[DomainEvent]


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
        keys, entries, events = timeline.keys, timeline.entries, timeline.events
        if size and key < keys[size - 1]:
            position = bisect_right(keys, key, 0, size)
            keys = [*keys[:position], key, *keys[position:size]]
            entries = [*entries[:position], (at, index, event), *entries[position:size]]
            events = [*events[:position], event, *events[position:size]]
        else:
            if len(keys) != size:
                keys, entries, events = keys[:size], entries[:size], events[:size]
            keys.append(key)
            entries.append((at, index, event))
            events.append(event)
        return _Timeline(index + 1, clock, size + 1, keys, entries, events)

    return step


_TIMELINE_FOLD: IncrementalFold[_Timeline] = IncrementalFold(
    lambda: _Timeline(0, None, 0, [], [], []), _timeline_folder(lambda _event: True), capacity=8
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
    lambda: _Timeline(0, None, 0, [], [], []),
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


def _timeline_since(
    history: Sequence[DomainEvent], since: datetime, now: datetime
) -> list[tuple[datetime, int, DomainEvent]]:
    """The entries of ``_timeline(history, now)`` timed at or after ``since``, in order."""
    timeline = _TIMELINE_FOLD(history)
    visible = bisect_right(timeline.keys, (now, timeline.seen), 0, timeline.size)
    # Positions are never negative, so this finds the first entry timed at ``since``.
    first = bisect_left(timeline.keys, (since, -1), 0, visible)
    return timeline.entries[first:visible]


class _SharedView(EventView, CombinedEvents):
    """A time-ordered view handed to every caller asking for it; it refuses changes."""

    __slots__ = ()


# Recent views by (timeline events list, length). A list's first items never change, so a
# view of the same list and length is the same view.
_VIEWS: dict[tuple[int, int], tuple[list[DomainEvent], EventView]] = {}
_VIEWS_LOCK = Lock()


def _timeline_events(history: Sequence[DomainEvent], now: datetime) -> EventView:
    """``[event for _, _, event in _timeline(history, now)]``, as a shared time-ordered view."""
    timeline = _TIMELINE_FOLD(history)
    visible = bisect_right(timeline.keys, (now, timeline.seen), 0, timeline.size)
    key = (id(timeline.events), visible)
    with _VIEWS_LOCK:
        cached = _VIEWS.get(key)
        if cached is not None and cached[0] is timeline.events:
            return cached[1]
        view = _SharedView(timeline.events[:visible])
        _VIEWS.pop(key, None)
        _VIEWS[key] = (timeline.events, view)
        while len(_VIEWS) > 4:
            del _VIEWS[next(iter(_VIEWS))]
        return view


class _EffortReplay:
    """activity_effort's running state after replaying the first ``count`` timeline entries.

    The replay depends only on the entry's identity and window and on the effort timeline.
    A timeline's ``entries`` list is append-only for as long as it is shared, so a replay
    of one list's prefix stays exact and later calls continue it from ``count`` instead of
    walking the whole life again.
    """

    __slots__ = (
        "entries",
        "count",
        "entry",
        "resource_id",
        "colleagues",
        "location",
        "awake",
        "scenes",
        "active_scenes",
        "companion_location",
        "occupied",
        "running",
        "cursor",
        "worked",
        "began",
        "resource",
        "window_start",
        "window_end",
    )

    def __init__(
        self,
        entries: list[tuple[datetime, int, DomainEvent]],
        entry: CalendarEntry,
        resource_id: str | None,
        colleagues: frozenset[str],
        window_start: datetime,
        window_end: datetime,
    ) -> None:
        self.entries = entries
        self.count = 0
        self.entry = entry
        self.resource_id = resource_id
        self.colleagues = colleagues
        self.location = "home"
        self.awake = False
        # Scenes Pathos joined, and those of them currently under way.
        self.scenes: set[str] = set()
        self.active_scenes: set[str] = set()
        self.companion_location: object = None
        self.occupied: set[str] = set()
        self.running = False
        self.cursor = window_start
        self.worked = 0.0
        self.began: str | None = None
        self.resource: dict[str, object] | None = None
        self.window_start = window_start
        self.window_end = window_end

    def reason(self) -> str | None:
        entry, resource = self.entry, self.resource
        # On a stay somewhere (Christmas at his parents'), sleeping there is being there.
        if not self.awake and entry.activity_type not in STAYS:
            return "asleep"
        if self.location != entry.location_id:
            return "elsewhere"
        if self.resource_id and (
            resource is None
            or resource.get("location_id") != self.location
            or resource.get("custodian_id") not in {"pathos", "community"}
            or resource.get("quantity") == 0
            or (entry.action != "repair" and resource.get("condition") == "broken")
            or (entry.action == "repair" and resource.get("condition") != "broken")
        ):
            return "resource_unavailable"
        if self.active_scenes:
            return "conversation"
        if self.occupied:
            return "interruption"
        if entry.companion_id and self.companion_location != entry.location_id:
            return "companion_absent"
        return None

    def advance(self, stop: int) -> None:
        entry, resource_id, colleagues = self.entry, self.resource_id, self.colleagues
        for at, _, event in self.entries[self.count : stop]:
            boundary = min(at, self.window_end)
            if self.running and boundary > self.cursor and self.reason() is None:
                self.worked += (boundary - self.cursor).total_seconds()
            self.cursor = max(self.cursor, boundary)
            p = event.payload
            if event.aggregate_id != "pathos":
                continue
            if event.kind == "pathos.travel_started":
                self.location = "in_transit"
            elif event.kind == "pathos.moved":
                self.location = str(p["location_id"])
            elif (
                resource_id
                and p.get("object_id") == resource_id
                and event.kind.startswith("object.")
            ):
                if event.kind == "object.registered":
                    self.resource = dict(p)
                elif self.resource is not None:
                    self.resource.update(
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
                self.running = False
            elif p.get("schedule_id") == entry.schedule_id and event.kind == "schedule.rescheduled":
                self.window_start = datetime.fromisoformat(str(p["starts_at"]))
                self.window_end = datetime.fromisoformat(str(p["ends_at"]))
                self.cursor = max(at, self.window_start)
                self.running = False
            elif event.kind == "sleep.started":
                self.awake = False
            elif event.kind == "sleep.ended":
                self.awake = True
            elif event.kind == "incident.response_started":
                self.occupied.add(str(p.get("incident_id")))
            elif event.kind == "phone.call_answered":
                self.occupied.add(f"phone:{p['call_id']}")
            elif event.kind == "phone.call_completed":
                self.occupied.discard(f"phone:{p['call_id']}")
            elif event.kind in {"incident.response_completed", "incident.response_abandoned"}:
                self.occupied.discard(str(p.get("incident_id")))
            elif (
                event.kind == "scene.started"
                and "pathos" in {p.get("initiator_id"), p.get("partner_id")}
                and not {p.get("initiator_id"), p.get("partner_id")} <= colleagues
                # Whoever drops in is talked to over the bench, or across the table.
                and not (_HERE in colleagues and p.get("location_id") == entry.location_id)
            ):
                self.scenes.add(str(p["scene_id"]))
                self.active_scenes.add(str(p["scene_id"]))
            elif event.kind in {"scene.ended", "scene.interrupted", "scene.resumed"}:
                if str(p.get("scene_id")) in self.scenes:
                    if event.kind == "scene.resumed":
                        self.active_scenes.add(str(p["scene_id"]))
                    else:
                        self.active_scenes.discard(str(p["scene_id"]))
            elif p.get("actor_id") == entry.companion_id and entry.companion_id:
                if event.kind == "npc.moved":
                    self.companion_location = p.get("location_id")
                elif event.kind == "npc.travel_started":
                    self.companion_location = None
            elif (
                event.kind == "activity.execution_started"
                and p.get("schedule_id") == entry.schedule_id
            ):
                self.running = True
                self.began = at.isoformat()
                self.cursor = max(self.window_start, at)
            elif (
                event.kind in {"activity.execution_paused", "activity.execution_resumed"}
                and p.get("schedule_id") == entry.schedule_id
            ):
                self.running = event.kind == "activity.execution_resumed"
                self.cursor = max(self.cursor, self.window_start, at)
                if self.running and p.get("resume_after"):
                    self.cursor = max(self.cursor, datetime.fromisoformat(str(p["resume_after"])))
        self.count = stop


_EFFORT_REPLAYS: OrderedDict[tuple[object, ...], list[_EffortReplay]] = OrderedDict()
_EFFORT_REPLAYS_LOCK = Lock()
_EFFORT_REPLAY_CAPACITY = 64
_EFFORT_REPLAYS_PER_ENTRY = 4


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
    # On a shift, talking with Ellis at the bench is part of the work, not a break from it;
    # and on a shift or an evening out, whoever else is there is talked to as part of it.
    colleagues = (
        frozenset({"pathos", EMPLOYER_ID, _HERE})
        if entry.schedule_id.startswith(ROTA_PREFIX)
        else frozenset({"pathos", _HERE})
        if entry.activity_type in SOCIABLE or entry.companion_id
        else frozenset({"pathos"})
    )
    resource_id = entry.target_id if entry.action == "repair" else entry.resource_id
    timeline = _EFFORT_FOLD(history)
    visible = bisect_right(timeline.keys, (now, timeline.seen), 0, timeline.size)
    key = (
        entry.schedule_id,
        entry.location_id,
        entry.action,
        entry.activity_type,
        entry.companion_id,
        resource_id,
        colleagues,
        window_start,
        window_end,
    )
    with _EFFORT_REPLAYS_LOCK:
        # History-ordered and time-ordered sequences keep separate timelines, so an entry
        # keeps a replay for each of the few timelines it was last asked about.
        replays = _EFFORT_REPLAYS.pop(key, [])
        replay = max(
            (r for r in replays if r.entries is timeline.entries and r.count <= visible),
            key=lambda r: r.count,
            default=None,
        )
        if replay is None:
            replay = _EffortReplay(
                timeline.entries, entry, resource_id, colleagues, window_start, window_end
            )
        else:
            replays.remove(replay)
        replay.advance(visible)
        _EFFORT_REPLAYS[key] = [replay, *replays[: _EFFORT_REPLAYS_PER_ENTRY - 1]]
        while len(_EFFORT_REPLAYS) > _EFFORT_REPLAY_CAPACITY:
            _EFFORT_REPLAYS.popitem(last=False)
        running, cursor, worked, began = replay.running, replay.cursor, replay.worked, replay.began
        window_start, window_end = replay.window_start, replay.window_end
        blocked_by = replay.reason()
    boundary = min(now, window_end)
    if running and boundary > cursor and blocked_by is None:
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
        "blocked_by": blocked_by,
        # Nearly there when the reserved time runs out, he stays the few extra minutes.
        "ready": began is not None
        and (
            worked + 0.001 >= required
            or (
                now >= window_end
                and worked >= FINISH_OFF_SHARE * required
                # Still there and free, or, on a long stint like a shift, just chatting at
                # the bench: the chat ends and he finishes up. Away, asleep or called off
                # to something else, it stays unfinished.
                and (
                    blocked_by is None
                    or (blocked_by == "conversation" and required >= LONG_STINT_SECONDS)
                )
            )
        ),
        "window_ended": now >= end,
        "is_working": running
        and blocked_by is None
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
        for at, _, e in _timeline_since(history, now - timedelta(hours=2), now)
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
