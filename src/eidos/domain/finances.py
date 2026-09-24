"""Replayable household money with source-linked, non-negative accounting."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold

_CATEGORIES = {
    "opening",
    "work_income",
    "cafe_meal",
    "provisions",
    "housing",
    "refund",
    "personal_purchase",
    "unexpected_expense",
    "everyday",
    "bills",
    "going_out",
    "gifts",
    "travel",
}


@dataclass(frozen=True, slots=True)
class FinancialTransaction:
    transaction_id: str
    amount_pence: int
    balance_pence: int
    category: str
    description: str
    source_event_id: str
    simulated_at: str


@dataclass(frozen=True, slots=True)
class MissedPayment:
    obligation_id: str
    amount_pence: int
    category: str
    reason: str
    simulated_at: str


@dataclass(frozen=True, slots=True)
class FinancialState:
    opened: bool = False
    balance_pence: int = 0
    transactions: dict[str, FinancialTransaction] = field(default_factory=dict)
    missed_payments: dict[str, MissedPayment] = field(default_factory=dict)

    def apply(self, event: DomainEvent) -> FinancialState:
        if not event.kind.startswith("finance."):
            return self
        transactions = dict(self.transactions)
        missed = dict(self.missed_payments)
        if event.kind == "finance.account_opened":
            if self.opened:
                raise ValueError("Household account is already open")
            if event.payload.get("currency") != "GBP":
                raise ValueError("Household account currency must be GBP")
            _aware_time(event, "simulated_at")
            opening = _integer(event, "opening_balance_pence", 0, 1_000_000)
            return FinancialState(True, opening, transactions, missed)
        if event.kind == "finance.transaction_recorded":
            if not self.opened:
                raise ValueError("A transaction requires an open household account")
            transaction_id = _required(event, "transaction_id")
            if transaction_id in transactions:
                raise ValueError("Financial transaction already exists")
            amount = _signed_integer(event, "amount_pence", 100_000)
            category = _required(event, "category")
            if category not in _CATEGORIES - {"opening"}:
                raise ValueError("Unknown transaction category")
            source_id = _required(event, "source_event_id")
            if event.causation_id is None or source_id != str(event.causation_id):
                raise ValueError("A transaction must cite its causal source event")
            at = _aware_time(event, "simulated_at")
            balance = self.balance_pence + amount
            if balance < 0:
                raise ValueError("Household balance cannot become negative")
            claimed = _integer(event, "balance_pence", 0, 1_000_000)
            if claimed != balance:
                raise ValueError("Transaction balance does not match the ledger")
            transactions[transaction_id] = FinancialTransaction(
                transaction_id,
                amount,
                balance,
                category,
                _required(event, "description"),
                source_id,
                at.isoformat(),
            )
            return FinancialState(True, balance, transactions, missed)
        if event.kind == "finance.payment_missed":
            if not self.opened:
                raise ValueError("A missed payment requires an open household account")
            obligation_id = _required(event, "obligation_id")
            if obligation_id in missed:
                raise ValueError("Missed payment already exists")
            amount = _integer(event, "amount_pence", 1, 100_000)
            category = _required(event, "category")
            if category not in _CATEGORIES - {"opening", "work_income", "refund"}:
                raise ValueError("Unknown missed-payment category")
            at = _aware_time(event, "simulated_at")
            source_id = _required(event, "source_event_id")
            if event.causation_id is None or source_id != str(event.causation_id):
                raise ValueError("A missed payment must cite its causal obligation")
            missed[obligation_id] = MissedPayment(
                obligation_id,
                amount,
                category,
                _required(event, "reason"),
                at.isoformat(),
            )
            return FinancialState(True, self.balance_pence, transactions, missed)
        return self


_FINANCES_FOLD: IncrementalFold[FinancialState] = IncrementalFold(
    lambda: FinancialState(), lambda state, event: state.apply(event)
)


def project_finances(events: Sequence[DomainEvent]) -> FinancialState:
    return _FINANCES_FOLD(events)


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Financial event requires {key}")
    return value


def _integer(event: DomainEvent, key: str, lower: int, upper: int) -> int:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
        raise ValueError(f"Financial {key} must be between {lower} and {upper} pence")
    return value


def _signed_integer(event: DomainEvent, key: str, maximum: int) -> int:
    value = event.payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value == 0 or abs(value) > maximum:
        raise ValueError(f"Financial {key} must be a bounded non-zero integer")
    return value


def _aware_time(event: DomainEvent, key: str) -> datetime:
    raw = _required(event, key)
    value = datetime.fromisoformat(raw)
    if value.utcoffset() is None:
        raise ValueError("Financial time must be timezone-aware")
    return value
