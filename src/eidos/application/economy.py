"""Household income, ordinary costs, obligations, and refunds."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from eidos.application.work_rota import SHIFT_WAGE_PENCE, is_rota_shift, partial_shift_wage
from eidos.domain.events import DomainEvent
from eidos.domain.finances import FinancialState
from eidos.domain.folding import events_of, kind_index

OPENING_BALANCE_PENCE = 40_000  # A modest cushion: a couple of weeks of rent and food.
CAFE_MEAL_PENCE = 600
PROVISIONS_PENCE = 2_400
WORKSHOP_SHIFT_PENCE = 3_200
WEEKLY_HOUSING_PENCE = 12_500  # Rent and bills for a small place in a market town.


def financial_foundation_events(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    if events_of(history, "finance.account_opened"):
        return []
    return [
        DomainEvent(
            "finance.account_opened",
            "pathos",
            {
                "currency": "GBP",
                "opening_balance_pence": OPENING_BALANCE_PENCE,
                "reason": "Starting household state",
                "simulated_at": at.isoformat(),
            },
            correlation_id="household-account",
        )
    ]


def financial_consequence_events(
    history: Sequence[DomainEvent], state: FinancialState, at: datetime
) -> list[DomainEvent]:
    """Resolve every eligible source once, then consider time-based obligations."""
    if not state.opened:
        return []
    output: list[DomainEvent] = []
    current = state
    processed = {transaction.source_event_id for transaction in current.transactions.values()}
    index = kind_index(history)
    processed.update(
        str(event.payload["source_event_id"])
        for event in index.of("finance.payment_missed")
        if isinstance(event.payload.get("source_event_id"), str)
    )
    opened_index = max(position for position, _ in index.positioned("finance.account_opened"))
    eligible = opened_index + 1
    for source in index.select(*_SOURCE_KINDS, start=eligible):
        source_id = str(source.event_id)
        if source_id in processed:
            continue
        consequence = _source_consequence(source)
        if consequence is None:
            continue
        amount, category, description = consequence
        if category == "refund":
            charged = _charged_order_was_cancelled(history, current, source)
            if charged is None:
                continue
            amount = charged
        if amount < 0 and current.balance_pence < -amount:
            missed = _missed_source_payment(source, amount, category, at)
            output.append(missed)
            current = current.apply(missed)
            processed.add(source_id)
            continue
        event = _transaction(source, current, amount, category, description, at)
        output.append(event)
        current = current.apply(event)
        processed.add(source_id)

    rota_world = at.hour == 17 and any(
        is_rota_shift(event.payload.get("schedule_id"))
        for event in index.of("schedule.created", eligible)
    )
    if at.hour == 17 and at.weekday() < 5 and not rota_world:
        # Authored-routine wages belong to worlds without a published rota; with one,
        # only actual shift evidence pays, so a routine memory can never double-pay.
        work = next(
            (
                event
                for event in reversed(index.of("memory.recorded", eligible))
                if event.payload.get("source") == "authored-routine"
                and event.payload.get("location_id") == "workshop"
                and _same_date(event, at)
                and str(event.event_id) not in processed
            ),
            None,
        )
        if work is not None:
            wage = _transaction(
                work,
                current,
                WORKSHOP_SHIFT_PENCE,
                "work_income",
                "Workshop shift income",
                at,
            )
            output.append(wage)
            current = current.apply(wage)

    week = at.isocalendar()
    obligation_id = f"housing:{week.year}-W{week.week:02d}"
    if (
        at.weekday() == 0
        and at.hour == 8
        and not any(event.payload.get("obligation_id") == obligation_id for event in history)
    ):
        due = DomainEvent(
            "finance.obligation_due",
            "pathos",
            {
                "obligation_id": obligation_id,
                "category": "housing",
                "amount_pence": WEEKLY_HOUSING_PENCE,
                "description": "Weekly housing and household costs",
                "simulated_at": at.isoformat(),
            },
            correlation_id=obligation_id,
        )
        output.append(due)
        if current.balance_pence >= WEEKLY_HOUSING_PENCE:
            payment = _transaction(
                due,
                current,
                -WEEKLY_HOUSING_PENCE,
                "housing",
                "Weekly housing and household costs",
                at,
            )
            output.append(payment)
        else:
            output.append(
                DomainEvent(
                    "finance.payment_missed",
                    "pathos",
                    {
                        "obligation_id": obligation_id,
                        "source_event_id": str(due.event_id),
                        "category": "housing",
                        "amount_pence": WEEKLY_HOUSING_PENCE,
                        "reason": "The household balance could not cover the weekly costs.",
                        "simulated_at": at.isoformat(),
                    },
                    causation_id=due.event_id,
                    correlation_id=obligation_id,
                )
            )
    return output


# The only kinds _source_consequence can turn into money.
_SOURCE_KINDS = (
    "want.purchased",
    "activity.completed",
    "activity.execution_unfinished",
    "meal.eaten",
    "object.replenishment_ordered",
    "object.replenishment_cancelled",
)


def _source_consequence(source: DomainEvent) -> tuple[int, str, str] | None:
    if source.kind == "want.purchased":
        price = source.payload.get("price_pence")
        if isinstance(price, int) and not isinstance(price, bool) and price > 0:
            return (-price, "personal_purchase", f"Bought {source.payload.get('item')}")
    if (
        source.kind == "activity.completed"
        and source.payload.get("activity") == "work"
        and is_rota_shift(source.payload.get("schedule_id"))
    ):
        return (SHIFT_WAGE_PENCE, "work_income", "Workshop shift wages")
    if source.kind == "activity.execution_unfinished" and is_rota_shift(
        source.payload.get("schedule_id")
    ):
        partial = partial_shift_wage(source.payload.get("worked_seconds"))
        if partial is not None:
            return (partial, "work_income", "Wages for the hours worked on a cut-short shift")
    if source.kind == "meal.eaten" and source.payload.get("provision_source") == "cafe_service":
        return (-CAFE_MEAL_PENCE, "cafe_meal", "Meal at Juniper Café")
    if (
        source.kind == "object.replenishment_ordered"
        and source.payload.get("object_id") == "household-provisions"
        and source.payload.get("attempt") == 1
    ):
        price = source.payload.get("price_pence", PROVISIONS_PENCE)
        amount = price if isinstance(price, int) and not isinstance(price, bool) else 0
        return (-amount, "provisions", "Household provisions order")
    if (
        source.kind == "object.replenishment_cancelled"
        and source.payload.get("object_id") == "household-provisions"
    ):
        return (PROVISIONS_PENCE, "refund", "Refund for undelivered provisions")
    return None


def _transaction(
    source: DomainEvent,
    state: FinancialState,
    amount: int,
    category: str,
    description: str,
    at: datetime,
) -> DomainEvent:
    source_id = str(source.event_id)
    return DomainEvent(
        "finance.transaction_recorded",
        "pathos",
        {
            "transaction_id": f"money:{source_id}",
            "amount_pence": amount,
            "balance_pence": state.balance_pence + amount,
            "category": category,
            "description": description,
            "source_event_id": source_id,
            "simulated_at": at.isoformat(),
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id or f"money:{source_id}",
    )


def _missed_source_payment(
    source: DomainEvent, amount: int, category: str, at: datetime
) -> DomainEvent:
    source_id = str(source.event_id)
    return DomainEvent(
        "finance.payment_missed",
        "pathos",
        {
            "obligation_id": f"money:{source_id}",
            "source_event_id": source_id,
            "category": category,
            "amount_pence": -amount,
            "reason": "The household balance could not cover this cost.",
            "simulated_at": at.isoformat(),
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id or f"money:{source_id}",
    )


def _same_date(event: DomainEvent, at: datetime) -> bool:
    raw = event.payload.get("simulated_at")
    return isinstance(raw, str) and datetime.fromisoformat(raw).date() == at.date()


def _charged_order_was_cancelled(
    history: Sequence[DomainEvent], state: FinancialState, cancellation: DomainEvent
) -> int | None:
    """The amount actually charged for a cancelled order, so refunds always match it."""
    order_id = cancellation.payload.get("order_id")
    order = next(
        (
            event
            for event in events_of(history, "object.replenishment_ordered")
            if event.payload.get("order_id") == order_id and event.payload.get("attempt") == 1
        ),
        None,
    )
    if order is None:
        return None
    return next(
        (
            -transaction.amount_pence
            for transaction in state.transactions.values()
            if transaction.source_event_id == str(order.event_id)
            and transaction.category == "provisions"
        ),
        None,
    )
