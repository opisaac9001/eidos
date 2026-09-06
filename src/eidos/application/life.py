"""A transactional scene loop. Role output is validated before becoming history."""

import asyncio
import math
from datetime import timedelta
from typing import Any

from eidos.application.cognition import perform
from eidos.application.first_story import story_events
from eidos.application.inner_life import active_concerns, waking_dream_events
from eidos.application.memory import memory_view, recall, terms
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.routine import beats_between
from eidos.domain.state import PathosState
from eidos.domain.world import LOCATIONS, PEOPLE, ROLES, location_name, npc_location
from eidos.domain.world_events import WorldEventKind, WorldEventProposal, resolve_world_event
from eidos.ports.event_store import EventStore
from eidos.ports.model_gateway import ModelGateway


def mood_name(energy: float, valence: float) -> str:
    if energy < 0.3:
        return "Sleepy"
    return "Content" if valence > 0.15 else "Reflective" if valence < -0.1 else "Quietly curious"


class Life:
    """Caller serializes operations; the store also rejects stale stream revisions."""

    def __init__(self, store: EventStore, gateway: ModelGateway, mode: str = "stand-in") -> None:
        self.store = store
        self.gateway = gateway
        self.mode = mode

    def history(self) -> list[DomainEvent]:
        return self.store.read("pathos")

    @staticmethod
    def project(history: list[DomainEvent]) -> PathosState:
        state = PathosState()
        for event in history:
            state = state.apply(event)
        return state

    def bootstrap(self) -> None:
        if self.history():
            return
        self.advance(8)

    def snapshot(self) -> dict[str, Any]:
        history = self.history()
        state = self.project(history)
        config = {"running": False, "minutes_per_tick": 15}
        weather = "Clear"
        relationships: dict[str, dict[str, Any]] = {
            person["id"]: {"encounters": 0, "trust": 0.3, "familiarity": 0.2, "tension": 0.0}
            for person in PEOPLE
        }
        roles: dict[str, dict[str, Any]] = {
            str(role["id"]): {**role, "calls": 0, "last": None, "status": "idle"} for role in ROLES
        }
        memories, feed, conversations, recalls = [], [], [], []
        diagnostics = []
        concerns = {}
        for event in history:
            payload = dict(event.payload)
            item = {
                **payload,
                "id": str(event.event_id),
                "kind": event.kind,
                "schema_version": event.schema_version,
                "causation_id": str(event.causation_id) if event.causation_id else None,
                "correlation_id": event.correlation_id,
            }
            if event.kind == "runtime.configured":
                config.update(payload)
            elif event.kind == "world.weather":
                weather = payload["text"]
            elif event.kind == "npc.encountered":
                person_id = payload["person_id"]
                relationships[person_id]["encounters"] += 1
                relationships[person_id]["familiarity"] = min(
                    1.0, relationships[person_id]["familiarity"] + 0.01
                )
            elif event.kind == "relationship.changed":
                relation = relationships[payload["person_id"]]
                for dimension in ("trust", "familiarity", "tension"):
                    relation[dimension] = max(
                        0.0,
                        min(1.0, relation[dimension] + float(payload.get(f"{dimension}_delta", 0))),
                    )
            elif event.kind == "concern.opened":
                concerns[payload["concern_id"]] = {**item, "status": "active"}
            elif event.kind == "concern.resolved" and payload["concern_id"] in concerns:
                concerns[payload["concern_id"]]["status"] = "resolved"
            elif event.kind == "role.completed":
                role = roles.get(payload["role"])
                if role:
                    role.update(
                        last=payload["simulated_at"],
                        status=payload["status"],
                        latency_ms=payload["latency_ms"],
                    )
                    role["calls"] += 1
                    role["failures"] = role.get("failures", 0) + (
                        payload["status"] in {"failed", "rejected"}
                    )
                    role["model"] = payload.get("model", "unknown")
                    role["error_code"] = payload.get("error_code")
                diagnostics.append(item)
            if event.kind == "memory.recorded":
                memories.append(item)
            if event.kind == "conversation.message":
                conversations.append(item)
            if event.kind == "memory.accessed":
                recalls.append(item)
            if event.kind in {
                "thought.recorded",
                "npc.encountered",
                "world.weather",
                "reflection.recorded",
                "dream.recorded",
                "dream.recalled",
                "day.summarized",
                "request.made",
                "intention.adopted",
                "intention.completed",
                "action.accepted",
                "action.rejected",
                "schedule.interrupted",
                "commitment.fulfilled",
                "relationship.changed",
                "memory.recorded",
                "role.failed",
                "memory.recovered",
            }:
                feed.append(item)
        population = [
            {
                **person,
                "location_id": npc_location(person["id"], state.simulated_at.hour),
                **relationships[person["id"]],
            }
            for person in PEOPLE
        ]
        memories = memory_view(history, state.simulated_at)
        planning = project_planning(history)
        return {
            "revision": len(history),
            "time": state.simulated_at.isoformat(),
            "day": (state.simulated_at.date() - PathosState().simulated_at.date()).days + 1,
            "pathos": {
                "name": "Pathos",
                "location_id": state.location_id,
                "location": location_name(state.location_id),
                "energy": state.energy,
                "valence": state.valence,
                "mood": mood_name(state.energy, state.valence),
            },
            "weather": weather,
            "config": config,
            "locations": LOCATIONS,
            "people": population,
            "roles": list(roles.values()),
            "diagnostics": list(reversed(diagnostics[-100:])),
            "goals": [vars_for(goal) for goal in planning.goals.values()],
            "commitments": [vars_for(item) for item in planning.commitments.values()],
            "calendar": [vars_for(item) for item in planning.calendar.values()],
            "objects": [vars_for(item) for item in planning.objects.values()],
            "intentions": [vars_for(item) for item in planning.intentions.values()],
            "concerns": list(concerns.values()),
            "memories": list(reversed(memories[-300:])),
            "recalls": list(reversed(recalls[-100:])),
            "feed": list(reversed(feed[-160:])),
            "conversations": conversations[-100:],
            "mode": self.mode,
            "model": getattr(self.gateway, "model", "authored-stand-in-v1"),
            "counts": {
                "events": len(history),
                "memories": len(memories),
                "conversations": len(conversations),
            },
        }

    def advance(self, hours: float) -> None:
        if (
            isinstance(hours, bool)
            or not isinstance(hours, (float, int))
            or not math.isfinite(hours)
            or not 0 < hours <= 24
        ):
            raise ValueError("Advance must be greater than zero and at most 24 hours")
        asyncio.run(self._advance(hours))

    async def _advance(self, hours: float) -> None:
        history = self.history()
        state = self.project(history)
        target = state.simulated_at + timedelta(hours=hours)
        if target <= state.simulated_at:
            raise ValueError("Advance is smaller than clock precision")
        pending = []
        beats = dict(beats_between(state.simulated_at, target))
        hour = state.simulated_at.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        times = []
        while hour <= target:
            times.append(hour)
            hour += timedelta(hours=1)
        for current in times:
            at = current.isoformat()
            pending.append(DomainEvent("time.advanced", "pathos", {"simulated_at": current}))
            state = state.apply(pending[-1])
            beat = beats.get(current)
            if beat:
                for event in (
                    DomainEvent("pathos.moved", "pathos", {"location_id": beat.location_id}),
                    DomainEvent("affect.changed", "pathos", {"energy": beat.energy}),
                ):
                    pending.append(event)
                    state = state.apply(event)
                pending.append(
                    DomainEvent(
                        "memory.recorded",
                        "pathos",
                        {
                            "text": beat.description,
                            "simulated_at": at,
                            "source": "authored-routine",
                            "category": "experience",
                            "location_id": beat.location_id,
                            "owner": "pathos",
                            "importance": 0.45,
                            "confidence": 1.0,
                        },
                    )
                )
            story = story_events(current, history + pending, state.location_id)
            if story:
                project_planning(history + pending + story)
                pending.extend(story)
            if current.hour == 7:
                waking = waking_dream_events(history + pending, state, at)
                for event in waking:
                    pending.append(event)
                    state = state.apply(event)
            planning_now = project_planning(history + pending)
            active_goal_ids = {
                goal.goal_id for goal in planning_now.goals.values() if goal.status == "active"
            }
            concerns_now = active_concerns(history + pending)
            recall_query = " ".join(
                [
                    location_name(state.location_id),
                    *(str(concern.payload["text"]) for concern in concerns_now[-2:]),
                    *(planning_now.goals[goal_id].title for goal_id in active_goal_ids),
                ]
            )
            selected_context = recall(
                history + pending,
                recall_query,
                current,
                7,
                entity_ids={state.location_id},
                goal_ids=active_goal_ids,
            )
            memories = [item.event.payload["text"] for item in selected_context]
            context = {
                "location": location_name(state.location_id),
                "time": at,
                "memories": memories,
            }
            if concerns_now:
                context["concern"] = concerns_now[-1].payload["text"]
            if current.hour in (6, 12, 18):
                text = await perform(self.gateway, "moira", context, at, pending)
                if text:
                    proposal = WorldEventProposal(
                        proposal_id=f"weather-{at}",
                        director_id="moira",
                        event_kind=WorldEventKind.WEATHER,
                        description=text,
                        location_id=state.location_id,
                        starts_at=current,
                        intensity=0.2,
                        expected_revision=len(history) + len(pending),
                        source=self.mode,
                    )
                    resolution = resolve_world_event(
                        proposal,
                        history=history + pending,
                        known_location_ids={str(place["id"]) for place in LOCATIONS},
                        actual_revision=len(history) + len(pending),
                        simulated_at=current,
                    )
                    pending.extend(resolution.events)
            if 7 <= current.hour < 23:
                text = await perform(self.gateway, "murmur", context, at, pending)
                if text:
                    pending.append(
                        DomainEvent(
                            "thought.recorded",
                            "pathos",
                            {
                                "text": text,
                                "simulated_at": at,
                                "source": self.mode,
                                "role": "murmur",
                            },
                        )
                    )
            if beat and state.location_id != "home":
                for person in PEOPLE:
                    if npc_location(person["id"], current.hour) != state.location_id:
                        continue
                    text = await perform(
                        self.gateway,
                        "firmament",
                        {**context, "person": person["name"]},
                        at,
                        pending,
                    )
                    if text:
                        encounter = DomainEvent(
                            "npc.encountered",
                            "pathos",
                            {
                                "person_id": person["id"],
                                "text": text,
                                "simulated_at": at,
                                "location_id": state.location_id,
                                "source": self.mode,
                                "role": "firmament",
                            },
                        )
                        pending.append(encounter)
                        memory = await perform(
                            self.gateway, "mnemosyne", {**context, "experience": text}, at, pending
                        )
                        recovered = memory is None
                        if recovered:
                            memory = text
                            pending.append(
                                DomainEvent(
                                    "memory.recovered",
                                    "pathos",
                                    {
                                        "text": "Archived the accepted encounter verbatim after the memory performer failed.",
                                        "simulated_at": at,
                                        "source_event_id": str(encounter.event_id),
                                        "source": "source-archive",
                                    },
                                )
                            )
                        if memory:
                            pending.append(
                                DomainEvent(
                                    "memory.recorded",
                                    "pathos",
                                    {
                                        "text": memory,
                                        "simulated_at": at,
                                        "category": "encounter",
                                        "source": "source-archive" if recovered else self.mode,
                                        "source_event_id": str(encounter.event_id),
                                        "location_id": state.location_id,
                                        "person_id": person["id"],
                                        "role": "source-archive" if recovered else "mnemosyne",
                                        "owner": "pathos",
                                        "importance": 0.75,
                                        "confidence": 1.0,
                                    },
                                )
                            )
                        state = state.apply(
                            DomainEvent(
                                "affect.changed",
                                "pathos",
                                {"valence": min(0.7, state.valence + 0.05)},
                            )
                        )
                        pending.append(
                            DomainEvent("affect.changed", "pathos", {"valence": state.valence})
                        )
            for role, scheduled_hour, kind in (
                ("reflection", 21, "reflection.recorded"),
                ("oneiros", 23, "dream.recorded"),
                ("chronicler", 23, "day.summarized"),
            ):
                if current.hour == scheduled_hour:
                    text = await perform(self.gateway, role, context, at, pending)
                    if text:
                        event = DomainEvent(
                            kind,
                            "pathos",
                            {
                                "text": text,
                                "simulated_at": at,
                                "source": self.mode,
                                "role": role,
                                **(
                                    {"seed_concern_id": concerns_now[-1].payload["concern_id"]}
                                    if role == "oneiros" and concerns_now
                                    else {}
                                ),
                            },
                        )
                        pending.append(event)
                        if role == "oneiros" and concerns_now:
                            pending.append(
                                DomainEvent(
                                    "dream.effect_scheduled",
                                    "pathos",
                                    {
                                        "source_dream_id": str(event.event_id),
                                        "simulated_at": at,
                                        "valence_delta": -0.05,
                                        "reason": "unresolved concern carried into sleep",
                                    },
                                )
                            )
        pending.append(DomainEvent("time.advanced", "pathos", {"simulated_at": target}))
        self.store.append("pathos", pending, expected_revision=len(history))

    def configure(self, running: bool, minutes_per_tick: int) -> None:
        if (
            type(running) is not bool
            or type(minutes_per_tick) is not int
            or minutes_per_tick not in (5, 15, 60)
        ):
            raise ValueError("Choose running true/false and a speed of 5, 15, or 60 minutes")
        history = self.history()
        self.store.append(
            "pathos",
            [
                DomainEvent(
                    "runtime.configured",
                    "pathos",
                    {"running": running, "minutes_per_tick": minutes_per_tick},
                )
            ],
            len(history),
        )

    def chat(self, text: str, request_id: str) -> None:
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValueError("Messages must contain 1–2000 characters")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
            raise ValueError("A request ID is required")
        history = self.history()
        previous = next(
            (
                e
                for e in history
                if e.kind == "conversation.message"
                and e.payload.get("request_id") == request_id
                and e.payload.get("speaker") == "you"
            ),
            None,
        )
        if previous:
            if previous.payload["text"] != text.strip():
                raise ValueError("Request ID was already used for a different message")
            return
        state = self.project(history)
        at = state.simulated_at.isoformat()
        pending = [
            DomainEvent(
                "conversation.message",
                "pathos",
                {
                    "text": text.strip(),
                    "speaker": "you",
                    "simulated_at": at,
                    "request_id": request_id,
                },
            )
        ]
        query_terms = terms(text)
        planning = project_planning(history)
        entity_ids = {
            str(entity["id"])
            for entity in (*PEOPLE, *LOCATIONS)
            if terms(str(entity["name"])) & query_terms or str(entity["id"]) in query_terms
        }
        entity_ids.update(
            item.object_id
            for item in planning.objects.values()
            if terms(item.name) & query_terms or item.object_id in query_terms
        )
        goal_ids = {
            goal.goal_id
            for goal in planning.goals.values()
            if goal.status == "active" and terms(goal.title) & query_terms
        }
        selected = recall(
            history,
            text.strip(),
            state.simulated_at,
            7,
            entity_ids=entity_ids,
            goal_ids=goal_ids,
        )
        context = {
            "message": text.strip(),
            "time": at,
            "location": location_name(state.location_id),
            "mood": mood_name(state.energy, state.valence),
            "memories": [item.event.payload["text"] for item in selected],
        }
        pending.extend(
            DomainEvent(
                "memory.accessed",
                "pathos",
                {
                    "memory_id": str(item.event.event_id),
                    "simulated_at": at,
                    "reason": item.reason,
                    "score": item.score,
                    "lexical_score": item.components["lexical"],
                    "entity_score": item.components["entity"],
                    "goal_score": item.components["goal"],
                    "accessibility_score": item.components["accessibility"],
                    "importance_score": item.components["importance"],
                    "confidence_score": item.components["confidence"],
                    "matched_entity_count": len(item.matched_entities),
                    "matched_goal_count": len(item.matched_goals),
                    "query_source": "user-conversation",
                },
            )
            for item in selected
        )
        reply = asyncio.run(perform(self.gateway, "pathos", context, at, pending))
        if reply:
            pending.append(
                DomainEvent(
                    "conversation.message",
                    "pathos",
                    {
                        "text": reply,
                        "speaker": "pathos",
                        "simulated_at": at,
                        "request_id": request_id,
                        "source": self.mode,
                    },
                )
            )
            pending.append(
                DomainEvent(
                    "memory.recorded",
                    "pathos",
                    {
                        "text": f"You visited and said: {text.strip()}",
                        "simulated_at": at,
                        "source": "user-conversation",
                        "source_event_id": str(pending[0].event_id),
                        "category": "conversation",
                        "location_id": state.location_id,
                        "owner": "pathos",
                        "importance": 0.7,
                        "confidence": 1.0,
                    },
                )
            )
        else:
            pending.append(
                DomainEvent(
                    "conversation.message",
                    "pathos",
                    {
                        "text": "Pathos couldn't produce a reply. Your message was saved; try sending again.",
                        "speaker": "system",
                        "simulated_at": at,
                        "request_id": request_id,
                        "source": "runtime",
                    },
                )
            )
        self.store.append("pathos", pending, len(history))


def vars_for(value: Any) -> dict[str, Any]:
    return {name: getattr(value, name) for name in value.__dataclass_fields__}
