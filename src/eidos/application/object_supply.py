"""Finite consumable stock, ordinary use, and non-magical replenishment."""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState


def object_supply_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    planning: PlanningState,
    *,
    pathos_awake: bool,
    pathos_location_id: str,
    pathos_energy: float,
    curiosity: float,
    values: Mapping[str, float],
    available_pence: int | None = None,
) -> list[DomainEvent]:
    """Resolve deliveries, then make at most one grounded use or replenishment choice."""
    pending = _pending_order(history)
    if (
        pending is not None
        and datetime.fromisoformat(str(pending.payload["due_at"])) <= simulated_at
    ):
        return _delivery_events(history, pending, simulated_at, planning, pathos_location_id)
    if not pathos_awake:
        return []
    if pending is None and 9 <= simulated_at.hour < 18:
        replenish = _replenishment_choice(
            history, simulated_at, planning, values, available_pence=available_pence
        )
        if replenish:
            return replenish
    if simulated_at.hour not in {16, 19}:
        return []
    return _consumption_choice(
        history,
        simulated_at,
        planning,
        pathos_location_id,
        pathos_energy,
        curiosity,
    )


def _consumption_choice(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    planning: PlanningState,
    location_id: str,
    energy: float,
    curiosity: float,
) -> list[DomainEvent]:
    handled = {
        (str(event.payload["object_id"]), str(event.payload["decision_date"]))
        for event in history
        if event.kind == "object.consumption_decided"
    }
    item = next(
        (
            value
            for value in planning.objects.values()
            if value.owner_id == "pathos"
            and value.custodian_id == "pathos"
            and value.location_id == location_id
            and value.quantity is not None
            and value.quantity > 0
            and value.unit != "meal portions"
            and (value.object_id, simulated_at.date().isoformat()) not in handled
        ),
        None,
    )
    if item is None or item.quantity is None:
        return []
    score = max(0.1, min(0.9, 0.25 + 0.3 * curiosity + 0.2 * (1 - energy)))
    sample = _sample(f"consume-{item.object_id}-{simulated_at.date().isoformat()}")
    use = sample < score
    registration = next(
        event
        for event in history
        if event.kind == "object.registered" and event.payload.get("object_id") == item.object_id
    )
    correlation = f"consume-{item.object_id}-{simulated_at.date().isoformat()}"
    decision = DomainEvent(
        "object.consumption_decided",
        "pathos",
        {
            "object_id": item.object_id,
            "decision_date": simulated_at.date().isoformat(),
            "decision": "use" if use else "save",
            "decision_score": score,
            "decision_sample": sample,
            "reason": "Pathos chose whether this finite supply fit the present moment.",
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=registration.event_id,
        correlation_id=correlation,
    )
    if not use:
        return [decision]
    consumed = DomainEvent(
        "object.consumed",
        "pathos",
        {
            "object_id": item.object_id,
            "quantity_used": 1,
            "unit": item.unit or "units",
            "location_id": location_id,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=decision.event_id,
        correlation_id=correlation,
    )
    stock = DomainEvent(
        "object.stock_changed",
        "pathos",
        {
            "object_id": item.object_id,
            "from_quantity": item.quantity,
            "quantity": item.quantity - 1,
            "reason": "One unit was actually used.",
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=consumed.event_id,
        correlation_id=correlation,
    )
    memory = DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": f"I used one {item.unit or 'unit'} from {item.name}.",
            "owner": "pathos",
            "category": "ordinary-use",
            "source": "deterministic-consequence",
            "source_event_id": str(consumed.event_id),
            "object_id": item.object_id,
            "location_id": location_id,
            "importance": 0.32,
            "confidence": 1.0,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=consumed.event_id,
        correlation_id=correlation,
    )
    return [decision, consumed, stock, memory]


def _replenishment_choice(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    planning: PlanningState,
    values: Mapping[str, float],
    *,
    available_pence: int | None,
) -> list[DomainEvent]:
    handled = {
        str(event.payload["source_stock_event_id"])
        for event in history
        if event.kind == "object.replenishment_decided"
    }
    stock_sources = [event for event in history if event.kind == "object.stock_changed"]
    for source in reversed(stock_sources):
        if str(source.event_id) in handled:
            continue
        object_id = str(source.payload["object_id"])
        item = planning.objects.get(object_id)
        if (
            item is None
            or item.quantity is None
            or item.reorder_at is None
            or item.quantity > item.reorder_at
        ):
            continue
        reliability = max(0.0, min(1.0, float(values.get("reliability", 0.5))))
        score = 0.25 + 0.55 * reliability
        sample = _sample(f"replenish-{object_id}-{item.quantity}-{source.event_id}")
        affordable = (
            item.unit != "meal portions" or available_pence is None or available_pence >= 2400
        )
        order = sample < score and affordable
        order_id = f"replenish-{source.event_id}"
        decision = DomainEvent(
            "object.replenishment_decided",
            "pathos",
            {
                "object_id": object_id,
                "source_stock_event_id": str(source.event_id),
                "decision": "order" if order else "go_without",
                "decision_score": score,
                "decision_sample": sample,
                "reason": (
                    "Pathos chose to replace the dwindling finite supply."
                    if order
                    else "The household balance could not cover new provisions."
                    if not affordable
                    else "Pathos chose to go without instead of automatically replenishing it."
                ),
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=source.event_id,
            correlation_id=order_id,
        )
        if not order:
            return [decision]
        due_at = simulated_at + timedelta(days=1)
        if item.unit == "meal portions":
            due_at = due_at.replace(hour=18, minute=0, second=0, microsecond=0)
        ordered = DomainEvent(
            "object.replenishment_ordered",
            "pathos",
            {
                "order_id": order_id,
                "object_id": object_id,
                "attempt": 1,
                "due_at": due_at.isoformat(),
                "restock_quantity": max(item.quantity + 1, item.reorder_at * 3),
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=decision.event_id,
            correlation_id=order_id,
        )
        return [decision, ordered]
    return []


def _pending_order(history: Sequence[DomainEvent]) -> DomainEvent | None:
    terminal = {
        str(event.payload["order_id"])
        for event in history
        if event.kind in {"object.replenishment_received", "object.replenishment_cancelled"}
    }
    latest: dict[str, DomainEvent] = {}
    for event in history:
        if event.kind == "object.replenishment_ordered":
            latest[str(event.payload["order_id"])] = event
    return next((event for key, event in latest.items() if key not in terminal), None)


def _delivery_events(
    history: Sequence[DomainEvent],
    order: DomainEvent,
    simulated_at: datetime,
    planning: PlanningState,
    location_id: str,
) -> list[DomainEvent]:
    order_id = str(order.payload["order_id"])
    object_id = str(order.payload["object_id"])
    item = planning.objects.get(object_id)
    if item is None or item.quantity is None:
        return []
    attempt = int(order.payload["attempt"])
    if location_id != item.location_id:
        missed = DomainEvent(
            "object.replenishment_missed",
            "pathos",
            {
                "order_id": order_id,
                "object_id": object_id,
                "attempt": attempt,
                "reason": "Pathos was not where the finite supply is kept.",
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=order.event_id,
            correlation_id=order_id,
        )
        if attempt >= 2:
            return [
                missed,
                DomainEvent(
                    "object.replenishment_cancelled",
                    "pathos",
                    {
                        "order_id": order_id,
                        "object_id": object_id,
                        "reason": "Both replenishment handoffs were missed.",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=missed.event_id,
                    correlation_id=order_id,
                ),
            ]
        retry = DomainEvent(
            "object.replenishment_ordered",
            "pathos",
            {
                **dict(order.payload),
                "attempt": 2,
                "due_at": (simulated_at + timedelta(days=1)).isoformat(),
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=missed.event_id,
            correlation_id=order_id,
        )
        return [missed, retry]
    received = DomainEvent(
        "object.replenishment_received",
        "pathos",
        {
            "order_id": order_id,
            "object_id": object_id,
            "attempt": attempt,
            "quantity_received": int(order.payload["restock_quantity"]) - item.quantity,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=order.event_id,
        correlation_id=order_id,
    )
    stock = DomainEvent(
        "object.stock_changed",
        "pathos",
        {
            "object_id": object_id,
            "from_quantity": item.quantity,
            "quantity": int(order.payload["restock_quantity"]),
            "reason": "A scheduled replenishment was physically received.",
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=received.event_id,
        correlation_id=order_id,
    )
    memory = DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": f"I received a replenishment of {item.name}.",
            "owner": "pathos",
            "category": "object-transfer",
            "source": "deterministic-consequence",
            "source_event_id": str(received.event_id),
            "object_id": object_id,
            "location_id": item.location_id,
            "importance": 0.4,
            "confidence": 1.0,
            "simulated_at": simulated_at.isoformat(),
        },
        causation_id=received.event_id,
        correlation_id=order_id,
    )
    return [received, stock, memory]


def _sample(key: str) -> float:
    return int(sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
