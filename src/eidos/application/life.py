"""A transactional scene loop. Role output is validated before becoming history."""

import asyncio
import math
from datetime import timedelta

from eidos.application.cognition import perform
from eidos.domain.events import DomainEvent
from eidos.domain.routine import beats_between
from eidos.domain.state import PathosState
from eidos.domain.world import LOCATIONS, PEOPLE, ROLES, location_name, npc_location
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

    def snapshot(self) -> dict:
        history = self.history()
        state = self.project(history)
        config = {"running": False, "minutes_per_tick": 15}
        weather = "Clear"
        relationships = {person["id"]: 0 for person in PEOPLE}
        roles = {role["id"]: {**role, "calls": 0, "last": None, "status": "idle"} for role in ROLES}
        memories, feed, conversations = [], [], []
        for event in history:
            payload = dict(event.payload)
            item = {**payload, "id": str(event.event_id), "kind": event.kind}
            if event.kind == "runtime.configured":
                config.update(payload)
            elif event.kind == "world.weather":
                weather = payload["text"]
            elif event.kind == "npc.encountered":
                person_id = payload["person_id"]
                relationships[person_id] = relationships.get(person_id, 0) + 1
            elif event.kind == "role.completed":
                role = roles.get(payload["role"])
                if role:
                    role.update(
                        last=payload["simulated_at"],
                        status=payload["status"],
                        latency_ms=payload["latency_ms"],
                    )
                    role["calls"] += 1
            if event.kind == "memory.recorded":
                memories.append(item)
            if event.kind == "conversation.message":
                conversations.append(item)
            if event.kind in {
                "thought.recorded",
                "npc.encountered",
                "world.weather",
                "reflection.recorded",
                "dream.recorded",
                "day.summarized",
                "memory.recorded",
                "role.failed",
            }:
                feed.append(item)
        population = [
            {
                **person,
                "location_id": npc_location(person["id"], state.simulated_at.hour),
                "encounters": relationships[person["id"]],
            }
            for person in PEOPLE
        ]
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
            "memories": list(reversed(memories[-300:])),
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
                        },
                    )
                )
            memories = [
                e.payload["text"] for e in history + pending if e.kind == "memory.recorded"
            ][-7:]
            context = {
                "location": location_name(state.location_id),
                "time": at,
                "memories": memories,
            }
            if current.hour in (6, 12, 18):
                text = await perform(self.gateway, "moira", context, at, pending)
                if text:
                    pending.append(
                        DomainEvent(
                            "world.weather",
                            "pathos",
                            {
                                "text": text,
                                "simulated_at": at,
                                "source": self.mode,
                                "role": "moira",
                            },
                        )
                    )
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
                        if memory:
                            pending.append(
                                DomainEvent(
                                    "memory.recorded",
                                    "pathos",
                                    {
                                        "text": memory,
                                        "simulated_at": at,
                                        "category": "encounter",
                                        "source": self.mode,
                                        "source_event_id": str(encounter.event_id),
                                        "location_id": state.location_id,
                                        "role": "mnemosyne",
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
                        pending.append(
                            DomainEvent(
                                kind,
                                "pathos",
                                {
                                    "text": text,
                                    "simulated_at": at,
                                    "source": self.mode,
                                    "role": role,
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
        context = {
            "message": text.strip(),
            "time": at,
            "location": location_name(state.location_id),
            "mood": mood_name(state.energy, state.valence),
            "memories": [e.payload["text"] for e in history if e.kind == "memory.recorded"][-7:],
        }
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
