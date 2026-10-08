"""Money he doesn't have to think about: his share options paid out.

At the software company in Bristol he had share options, the way early staff often do.
The company has been bought (which is why their docs person left, and why they wanted him
back to rewrite the docs), and his options pay out: a couple of days after the docs offer
an email explains it, and a week later the money lands. He does the sensible thing he's read
about: most of it goes into index funds, a few thousand stays to hand. From then on money is
tracked, not worried about.

- The investments are their own pot, valued at the start of each month: up a little most
  months, down some, the way markets go.
- When his current account runs low he moves money across, a thousand at a time, each
  move a transaction in the household ledger like any other.
- He works because he likes it, and chooses what he takes on.

It's understated, like him: he'd rather people didn't know.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.application.bookings import remember
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

NOTICE = "finance.windfall_notice"
LANDED = "finance.windfall"
VALUED = "finance.investments_valued"
MOVED = "finance.moved_from_investments"
SAVED = "finance.moved_to_investments"
SWEEP_ABOVE_PENCE = 700_000
GROSS_PENCE = 61_200_000  # his options, before tax
NET_PENCE = 54_830_000  # after capital gains tax
KEEP_TO_HAND_PENCE = 400_000
TOP_UP_BELOW_PENCE = 300_000
TOP_UP_PENCE = 100_000  # the most one ledger transaction carries
COMFORTABLE_PENCE = 10_000_000
NOTICE_AFTER = timedelta(days=2)
LANDS_AFTER = timedelta(days=7)


def _when(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def invested_pence(history: Sequence[DomainEvent]) -> int:
    """What the investments are worth now."""
    value = 0
    for event in events_of(history, LANDED, VALUED, MOVED, SAVED):
        if event.kind == LANDED:
            value += int(event.payload.get("invested_pence", 0) or 0)
        elif event.kind == SAVED:
            value += int(event.payload.get("amount_pence", 0) or 0)
        elif event.kind == VALUED:
            value = int(event.payload.get("value_pence", value) or 0)
        else:
            value -= int(event.payload.get("amount_pence", 0) or 0)
    return max(0, value)


def comfortable(history: Sequence[DomainEvent]) -> bool:
    """Whether money is something he needn't think about."""
    return invested_pence(history) >= COMFORTABLE_PENCE


def wealth_view(history: Sequence[DomainEvent]) -> dict[str, object] | None:
    if not events_of(history, LANDED):
        return None
    valued = events_of(history, VALUED)[-1:]
    return {
        "invested_pence": invested_pence(history),
        "valued_at": str(valued[0].payload["simulated_at"]) if valued else None,
        "last_month_change_pence": int(valued[0].payload.get("change_pence", 0)) if valued else 0,
        "moved_to_current_account_pence": sum(
            int(e.payload.get("amount_pence", 0) or 0) for e in events_of(history, MOVED)
        ),
    }


def money_in_words(history: Sequence[DomainEvent], balance_pence: int) -> str | None:
    """How he'd think of his money, for his voice."""
    if not comfortable(history):
        return None
    invested = invested_pence(history)
    return (
        f"Comfortable, and a bit embarrassed about it: about £{balance_pence // 100:,} in the "
        f"bank and around £{round(invested / 100, -3):,.0f} in index funds since my old "
        "company's share options paid out. Money's tracked, not worried about. I don't "
        "talk about it much."
    )


def wealth_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    balance_pence: int,
) -> list[DomainEvent]:
    """The payout, the investments month by month, and topping up his current account."""
    offers = events_of(history, "career.offer_received")
    if not offers:
        return []
    notice = events_of(history, NOTICE)
    if not notice:
        if not awake or not 9 <= at.hour <= 19 or at - _when(offers[0]) < NOTICE_AFTER:
            return []
        told = DomainEvent(
            NOTICE,
            "pathos",
            {"gross_pence": GROSS_PENCE, "net_pence": NET_PENCE, "simulated_at": at.isoformat()},
        )
        return [
            told,
            remember(
                told,
                "An email from my old company: they've been bought, which explains the docs "
                "person leaving. My share options pay out. I read the number three times. "
                "After tax it's more money than I ever expected to have. Haven't told anyone.",
                at, 0.85, origin="lived-money", category="experience",
            ),
        ]  # fmt: skip
    landed = events_of(history, LANDED)
    if not landed:
        if not awake or at - _when(notice[0]) < LANDS_AFTER or not 9 <= at.hour <= 17:
            return []
        money = DomainEvent(
            LANDED,
            "pathos",
            {
                "net_pence": NET_PENCE,
                "invested_pence": NET_PENCE,
                "simulated_at": at.isoformat(),
            },
        )
        return [
            money,
            remember(
                money,
                "The share money landed. Put it straight into index funds, like every sensible "
                "article says, and moved a few thousand into my current account so I stop "
                "checking. Still doesn't feel real.",
                at, 0.8, origin="lived-money", category="experience",
            ),
            *_top_up(history, money, at, balance_pence, upto=KEEP_TO_HAND_PENCE),
        ]  # fmt: skip
    output: list[DomainEvent] = []
    # The start of each month: what the investments are worth now.
    month = at.strftime("%Y-%m")
    if (
        at.day == 1
        and at.hour == 8
        and not any(str(e.payload.get("month")) == month for e in events_of(history, VALUED)[-2:])
    ):
        before = invested_pence(history)
        # Most months up a little, some down: about 6% a year, with the wobble.
        change = round(before * (0.005 + (_roll("market", month) - 0.5) * 0.06))
        output.append(
            DomainEvent(
                VALUED,
                "pathos",
                {
                    "month": month,
                    "value_pence": before + change,
                    "change_pence": change,
                    "simulated_at": at.isoformat(),
                },
            )
        )
    if balance_pence < TOP_UP_BELOW_PENCE and at.weekday() == 0 and at.hour == 9:
        output += _top_up(history, None, at, balance_pence, upto=KEEP_TO_HAND_PENCE)
    # More than he needs sitting in the current account goes back in, at the month's start.
    if at.day == 1 and at.hour == 9:
        balance = balance_pence
        while balance - TOP_UP_PENCE >= SWEEP_ABOVE_PENCE and len(output) < 6:
            output.append(
                DomainEvent(
                    SAVED,
                    "pathos",
                    {
                        "amount_pence": TOP_UP_PENCE,
                        "transfer_id": f"save-{at.isoformat()}-{len(output)}",
                        "simulated_at": at.isoformat(),
                    },
                )
            )
            balance -= TOP_UP_PENCE
    return output


def _top_up(
    history: Sequence[DomainEvent],
    cause: DomainEvent | None,
    at: datetime,
    balance_pence: int,
    *,
    upto: int,
) -> list[DomainEvent]:
    """Moving money into his current account, a thousand at a time."""
    available = invested_pence(history) + (int(cause.payload["invested_pence"]) if cause else 0)
    output: list[DomainEvent] = []
    balance = balance_pence
    while balance + TOP_UP_PENCE <= upto and available >= TOP_UP_PENCE and len(output) < 4:
        moved = DomainEvent(
            MOVED,
            "pathos",
            {
                "amount_pence": TOP_UP_PENCE,
                "transfer_id": f"move-{at.isoformat()}-{len(output)}",
                "simulated_at": at.isoformat(),
            },
            causation_id=cause.event_id if cause is not None else None,
        )
        output.append(moved)
        balance += TOP_UP_PENCE
        available -= TOP_UP_PENCE
    return output
