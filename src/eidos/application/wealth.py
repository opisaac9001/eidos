"""His money, managed the way a sensible person in England manages a windfall.

At the small Bristol software company he joined after university everyone was given share
options he assumed would come to nothing. The company has been bought (why their docs
person left), and his options pay out. Then the ordinary, unglamorous business of having
money:

- **Accounts.** His current account (the household ledger, where daily life is spent), an
  easy-access savings account with his emergency fund, a separate savings pot for tax, a
  stocks and shares ISA, and a general investment account. Both investment accounts hold
  the same global index fund.
- **Tax.** Capital gains tax on the shares (18% above the annual exempt amount, with
  Business Asset Disposal Relief) is put aside the evening he sorts the money out and paid
  with his self-assessment by 31 January after the tax year ends. A quarter of every
  freelance payment goes into the tax pot as it arrives. He does the return in January,
  later than he meant to.
- **Month to month.** Savings pay interest; the fund goes up most months and down some.
  When his current account runs low he moves money across from savings, a thousand at a
  time; when it builds up, it goes back. Each 6 April he moves another year's ISA allowance
  across. On the first Sunday of the month he sits down and looks at it all.

Money is tracked, not worried about. Every move into or out of his current account is an
ordinary ledger transaction; the other accounts are folded from their own events. He's
understated about it and would rather people didn't know.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.application.bookings import remember
from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, events_of

NOTICE = "finance.windfall_notice"
LANDED = "finance.windfall"
SORTED = "finance.money_sorted"
MONTH = "finance.month_valued"
FROM_SAVINGS = "finance.moved_from_savings"
TO_SAVINGS = "finance.moved_to_savings"
TAX_SET_ASIDE = "finance.tax_set_aside"
TAX_RETURN = "finance.tax_return_done"
TAX_PAID = "finance.tax_paid"
ISA_TOP_UP = "finance.isa_topped_up"
MONEY_CHECK = "finance.money_checked"
KINDS = (LANDED, SORTED, MONTH, FROM_SAVINGS, TO_SAVINGS, TAX_SET_ASIDE, TAX_PAID, ISA_TOP_UP)

GROSS_PENCE = 61_200_000
CGT_EXEMPT_PENCE = 300_000
CGT_RATE = 0.18
EMERGENCY_FUND_PENCE = 2_500_000
ISA_ALLOWANCE_PENCE = 2_000_000
SAVINGS_RATE = 0.039  # easy access, a year
FUND_GROWTH = 0.06  # a year, on average, with the wobble
PERSONAL_ALLOWANCE_PENCE = 1_257_000
TAX_SHARE_OF_FREELANCE = 0.25
LOW_PENCE = 150_000
TOPPED_TO_PENCE = 300_000
HIGH_PENCE = 600_000
SWEPT_TO_PENCE = 500_000
TRANSFER_PENCE = 100_000  # the most one ledger transaction carries
COMFORTABLE_PENCE = 10_000_000
NOTICE_AFTER = timedelta(days=2)
LANDS_AFTER = timedelta(days=7)
# How he'd put where it went.
_SPENT_ON = {
    "everyday": "bits and pieces",
    "provisions": "food shopping",
    "going_out": "going out",
    "cafe_meal": "cafés",
    "takeaway": "takeaways",
    "personal_purchase": "things I wanted",
    "gifts": "presents",
    "travel": "travel",
    "bills": "bills",
    "unexpected_expense": "something going wrong",
}
# Ledger categories that are money moved about, not spent.
_MOVES = frozenset({"savings_transfer", "tax_set_aside"})


@dataclass(frozen=True, slots=True)
class Accounts:
    savings: int = 0
    tax_pot: int = 0
    isa: int = 0
    general: int = 0
    tax_owed: int = 0  # capital gains tax due on the shares, until it's paid
    gain_tax_year: str = ""


def _when(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _pence(event: DomainEvent, key: str) -> int:
    value = event.payload.get(key, 0)
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _step(held: Accounts, event: DomainEvent) -> Accounts:
    if event.kind not in KINDS:
        return held
    if event.kind == LANDED:
        return replace(
            held,
            savings=held.savings + _pence(event, "gross_pence"),
            tax_owed=_pence(event, "cgt_pence"),
            gain_tax_year=str(event.payload.get("tax_year", "")),
        )
    if event.kind == SORTED:
        return replace(
            held,
            savings=_pence(event, "savings_pence"),
            tax_pot=held.tax_pot + _pence(event, "tax_pot_pence"),
            isa=held.isa + _pence(event, "isa_pence"),
            general=held.general + _pence(event, "general_pence"),
        )
    if event.kind == MONTH:
        return replace(
            held,
            savings=held.savings + _pence(event, "savings_interest_pence"),
            tax_pot=held.tax_pot + _pence(event, "tax_pot_interest_pence"),
            isa=held.isa + _pence(event, "isa_change_pence"),
            general=held.general + _pence(event, "general_change_pence"),
        )
    if event.kind == FROM_SAVINGS:
        return replace(held, savings=held.savings - _pence(event, "amount_pence"))
    if event.kind == TO_SAVINGS:
        return replace(held, savings=held.savings + _pence(event, "amount_pence"))
    if event.kind == TAX_SET_ASIDE:
        return replace(held, tax_pot=held.tax_pot + _pence(event, "amount_pence"))
    if event.kind == TAX_PAID:
        return replace(
            held,
            tax_pot=held.tax_pot - _pence(event, "amount_pence"),
            tax_owed=0 if event.payload.get("includes_gain") else held.tax_owed,
        )
    moved = _pence(event, "amount_pence")  # ISA top-up
    return replace(held, isa=held.isa + moved, general=held.general - moved)


_ACCOUNTS: IncrementalFold[Accounts] = IncrementalFold(Accounts, _step)


def accounts(history: Sequence[DomainEvent]) -> Accounts:
    return _ACCOUNTS(history)


def invested_pence(history: Sequence[DomainEvent]) -> int:
    held = accounts(history)
    return held.isa + held.general


def comfortable(history: Sequence[DomainEvent]) -> bool:
    """Whether money is something he needn't think about."""
    held = accounts(history)
    return held.savings + held.isa + held.general >= COMFORTABLE_PENCE


def tax_year(day: date) -> str:
    """'2026-27' for 6 April 2026 to 5 April 2027."""
    start = day.year if (day.month, day.day) >= (4, 6) else day.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def _pounds(pence: int) -> str:
    return f"£{pence // 100:,}"


def _round_pounds(pence: int, to: int = 1000) -> str:
    return f"£{round(pence / 100 / to) * to:,}"


def wealth_view(history: Sequence[DomainEvent]) -> dict[str, object] | None:
    """His accounts for the page."""
    if not events_of(history, LANDED):
        return None
    held = accounts(history)
    month = events_of(history, MONTH)[-1:]
    return {
        "savings_pence": held.savings,
        "tax_pot_pence": held.tax_pot,
        "isa_pence": held.isa,
        "general_investments_pence": held.general,
        "tax_owed_pence": held.tax_owed,
        "last_month": dict(month[0].payload) if month else None,
    }


def money_in_words(history: Sequence[DomainEvent], balance_pence: int) -> str | None:
    """How he'd think of his money, for his voice."""
    if not comfortable(history):
        return None
    held = accounts(history)
    return (
        "Comfortable, and a bit embarrassed about it, since my old company's share options "
        f"paid out: about {_pounds(balance_pence)} in my current account, "
        f"{_round_pounds(held.savings)} in savings, around "
        f"{_round_pounds(held.isa + held.general, 10_000)} in index funds"
        + (f", and {_round_pounds(held.tax_pot)} put aside for tax" if held.tax_pot else "")
        + ". I look at it once a month and don't talk about it."
    )


def _note(cause: DomainEvent, text: str, at: datetime, importance: float) -> DomainEvent:
    return remember(cause, text, at, importance, origin="lived-money", category="experience")


def _transfers(kind: str, total: int, at: datetime, cause: DomainEvent | None) -> list[DomainEvent]:
    """Money into or out of his current account, in ledger-sized moves."""
    output: list[DomainEvent] = []
    left = total
    while left > 0 and len(output) < 6:
        amount = min(TRANSFER_PENCE, left)
        output.append(
            DomainEvent(
                kind,
                "pathos",
                {
                    "amount_pence": amount,
                    "transfer_id": f"{kind}-{at.isoformat()}-{len(output)}",
                    "simulated_at": at.isoformat(),
                },
                causation_id=cause.event_id if cause is not None else None,
            )
        )
        left -= amount
    return output


def wealth_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    balance_pence: int,
    ledger: Sequence[tuple[str, int, str]] = (),
) -> list[DomainEvent]:
    """The payout, then month by month money looked after.

    ``ledger`` is his current account's recent (time, amount, category), for the monthly
    look at where it went.
    """
    offers = events_of(history, "career.offer_received")
    if not offers:
        return []
    notice = events_of(history, NOTICE)
    if not notice:
        if not awake or not 9 <= at.hour <= 19 or at - _when(offers[0]) < NOTICE_AFTER:
            return []
        cgt = round((GROSS_PENCE - CGT_EXEMPT_PENCE) * CGT_RATE)
        told = DomainEvent(
            NOTICE,
            "pathos",
            {"gross_pence": GROSS_PENCE, "cgt_pence": cgt, "simulated_at": at.isoformat()},
        )
        return [
            told,
            _note(
                told,
                "An email from my old company: they've been bought, which explains the docs "
                "person leaving. My share options pay out: "
                f"{_round_pounds(GROSS_PENCE)} before tax. I read the number three times. "
                "Haven't told anyone.",
                at, 0.85,
            ),
        ]  # fmt: skip
    landed = events_of(history, LANDED)
    if not landed:
        if not awake or at - _when(notice[0]) < LANDS_AFTER or not 9 <= at.hour <= 17:
            return []
        cgt = _pence(notice[0], "cgt_pence")
        money = DomainEvent(
            LANDED,
            "pathos",
            {
                "gross_pence": GROSS_PENCE,
                "cgt_pence": cgt,
                "tax_year": tax_year(at.date()),
                "simulated_at": at.isoformat(),
            },
        )
        return [
            money,
            _note(
                money,
                "The share money landed in my savings account. "
                f"About {_round_pounds(cgt)} of it is the tax man's, come the January after "
                "next. Still doesn't feel real.",
                at, 0.8,
            ),
        ]  # fmt: skip
    if not events_of(history, SORTED):
        # An evening or two later, sitting down to do it properly.
        if not awake or not 19 <= at.hour <= 21 or at - _when(landed[0]) < timedelta(hours=20):
            return []
        held = accounts(history)
        tax = held.tax_owed
        general = held.savings - EMERGENCY_FUND_PENCE - tax - ISA_ALLOWANCE_PENCE
        done = DomainEvent(
            SORTED,
            "pathos",
            {
                "savings_pence": EMERGENCY_FUND_PENCE,
                "tax_pot_pence": tax,
                "isa_pence": ISA_ALLOWANCE_PENCE,
                "general_pence": general,
                "simulated_at": at.isoformat(),
            },
        )
        return [
            done,
            _note(
                done,
                "Spent the evening sorting the money properly, like the articles say: "
                f"{_round_pounds(tax)} into a separate pot for the tax bill, twenty grand into "
                f"a stocks and shares ISA, {_round_pounds(EMERGENCY_FUND_PENCE)} left in "
                "easy-access savings, and the rest into a general account, all in the same "
                "boring global index fund. Then I went for a walk.",
                at, 0.6,
            ),
            *_transfers(FROM_SAVINGS, max(0, TOPPED_TO_PENCE - balance_pence), at, done),
        ]  # fmt: skip
    output: list[DomainEvent] = []
    output += _month(history, at)
    output += _set_aside(history, at)
    output += _current_account(at, balance_pence, output)
    output += _tax(history, at, awake)
    output += _isa(history, at)
    output += _money_check(history, at, awake, ledger)
    return output


def _month(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    """The first of the month: interest paid, the fund valued."""
    month = at.strftime("%Y-%m")
    if at.day != 1 or at.hour != 8:
        return []
    if any(str(e.payload.get("month")) == month for e in events_of(history, MONTH)[-2:]):
        return []
    held = accounts(history)
    rate = SAVINGS_RATE / 12
    # Most months up a little, some down.
    market = FUND_GROWTH / 12 + (_roll("market", month) - 0.5) * 0.07
    return [
        DomainEvent(
            MONTH,
            "pathos",
            {
                "month": month,
                "savings_interest_pence": round(held.savings * rate),
                "tax_pot_interest_pence": round(held.tax_pot * rate),
                "isa_change_pence": round(held.isa * market),
                "general_change_pence": round(held.general * market),
                "fund_return": round(market, 4),
                "simulated_at": at.isoformat(),
            },
        )
    ]


def _set_aside(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    """A quarter of each freelance payment, into the tax pot, as it arrives."""
    done = {str(e.payload.get("for_event_id")) for e in events_of(history, TAX_SET_ASIDE)[-20:]}
    for paid in events_of(history, "freelance.paid")[-6:]:
        if str(paid.event_id) in done or at - _when(paid) > timedelta(hours=3):
            continue
        amount = min(TRANSFER_PENCE, round(_pence(paid, "fee_pence") * TAX_SHARE_OF_FREELANCE))
        if amount <= 0:
            continue
        return [
            DomainEvent(
                TAX_SET_ASIDE,
                "pathos",
                {
                    "amount_pence": amount,
                    "for_event_id": str(paid.event_id),
                    "simulated_at": at.isoformat(),
                },
                causation_id=paid.event_id,
            )
        ]
    return []


def _current_account(
    at: datetime, balance_pence: int, output: Sequence[DomainEvent]
) -> list[DomainEvent]:
    """Topped up from savings when it runs low, swept back when it builds up."""
    balance = balance_pence - sum(
        _pence(e, "amount_pence") for e in output if e.kind == TAX_SET_ASIDE
    )
    if balance < LOW_PENCE and at.hour == 9:
        return _transfers(FROM_SAVINGS, TOPPED_TO_PENCE - balance, at, None)
    if balance > HIGH_PENCE and at.day == 1 and at.hour == 9:
        return _transfers(TO_SAVINGS, balance - SWEPT_TO_PENCE, at, None)
    return []


def _tax(history: Sequence[DomainEvent], at: datetime, awake: bool) -> list[DomainEvent]:
    """Self-assessment: the return in January, a bit late, then the bill by the 31st."""
    if at.month != 1:
        return []
    previous = f"{at.year - 2}-{str(at.year - 1)[2:]}"  # the tax year that ended last April
    if any(e.payload.get("tax_year") == previous for e in events_of(history, TAX_PAID)):
        return []
    held = accounts(history)
    start = datetime(at.year - 2, 4, 6, tzinfo=at.tzinfo)
    end = datetime(at.year - 1, 4, 6, tzinfo=at.tzinfo)
    earned = sum(
        _pence(e, "fee_pence") for e in events_of(history, "freelance.paid") if start <= _when(e) < end
    )  # fmt: skip
    interest = sum(
        _pence(e, "savings_interest_pence") + _pence(e, "tax_pot_interest_pence")
        for e in events_of(history, MONTH)
        if start <= _when(e) < end
    )
    income_tax = round(max(0, earned - PERSONAL_ALLOWANCE_PENCE) * 0.26)  # 20% tax, 6% NI
    interest_tax = round(max(0, interest - 100_000) * 0.2)  # above the savings allowance
    gain = held.tax_owed if held.gain_tax_year == previous else 0
    bill = income_tax + interest_tax + gain
    if bill <= 0:
        return []
    returns = [e for e in events_of(history, TAX_RETURN) if e.payload.get("tax_year") == previous]
    if not returns:
        # Some time in the second half of January, never early.
        if not awake or at.hour != 20 or at.day < 12 + int(_roll("return", previous) * 15):
            return []
        filed = DomainEvent(
            TAX_RETURN,
            "pathos",
            {"tax_year": previous, "bill_pence": bill, "simulated_at": at.isoformat()},
        )
        return [
            filed,
            _note(filed, f"Did my tax return for {previous}, finally. {_pounds(bill)} to pay by "
                  "the end of the month. The money's sitting there ready, which helps.", at, 0.5),
        ]  # fmt: skip
    if at.day < 25 or at.hour != 10 or held.tax_pot <= 0:
        return []
    amount = min(bill, held.tax_pot)
    tax = DomainEvent(
        TAX_PAID,
        "pathos",
        {
            "tax_year": previous,
            "amount_pence": amount,
            "includes_gain": bool(gain),
            "simulated_at": at.isoformat(),
        },
    )
    words = (
        f"Paid the tax bill: {_pounds(amount)}, most of it on the shares. Watching that much "
        "leave in one go is something."
        if gain
        else f"Paid my tax bill: {_pounds(amount)}. The tax pot had it covered."
    )
    return [tax, _note(tax, words, at, 0.55 if gain else 0.4)]


def _isa(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    """A new tax year: another year's ISA allowance across from the general account."""
    if (at.month, at.day, at.hour) != (4, 6, 10):
        return []
    year = tax_year(at.date())
    if any(e.payload.get("tax_year") == year for e in events_of(history, ISA_TOP_UP)):
        return []
    amount = min(ISA_ALLOWANCE_PENCE, accounts(history).general)
    if amount <= 0:
        return []
    moved = DomainEvent(
        ISA_TOP_UP,
        "pathos",
        {"tax_year": year, "amount_pence": amount, "simulated_at": at.isoformat()},
    )
    return [moved, _note(moved, "New tax year, so another twenty grand into the ISA. The most "
                         "grown-up thing I'll do all month.", at, 0.3)]  # fmt: skip


def _money_check(
    history: Sequence[DomainEvent],
    at: datetime,
    awake: bool,
    ledger: Sequence[tuple[str, int, str]],
) -> list[DomainEvent]:
    """The first Sunday of the month: a look at where it went."""
    if at.weekday() != 6 or at.day > 7 or at.hour != 19 or not awake:
        return []
    month = at.strftime("%Y-%m")
    if any(e.payload.get("month") == month for e in events_of(history, MONEY_CHECK)[-2:]):
        return []
    this_month = at.replace(day=1).date().isoformat()
    last_month = (at.replace(day=1) - timedelta(days=1)).replace(day=1).date().isoformat()
    lines = [
        (amount, kind) for when, amount, kind in ledger if last_month <= when[:10] < this_month
    ]
    spent = -sum(amount for amount, kind in lines if amount < 0 and kind not in _MOVES)
    earned = sum(amount for amount, kind in lines if amount > 0 and kind == "work_income")
    by_kind: dict[str, int] = {}
    for amount, kind in lines:
        if amount < 0 and kind not in _MOVES | {"housing"}:
            by_kind[kind] = by_kind.get(kind, 0) - amount
    top = max(by_kind, key=lambda kind: by_kind[kind], default=None)
    fund = events_of(history, MONTH)[-1:]
    went = float(fund[0].payload.get("fund_return", 0)) if fund else 0.0
    looked = DomainEvent(
        MONEY_CHECK,
        "pathos",
        {
            "month": month,
            "spent_pence": spent,
            "earned_pence": earned,
            "simulated_at": at.isoformat(),
        },
    )
    words = (
        f"Did my monthly money look: spent {_pounds(spent)} last month"
        + (f", mostly {_SPENT_ON.get(top, top.replace('_', ' '))} after the rent" if top else "")
        + (f", and earned {_pounds(earned)} writing" if earned else "")
        + ". The fund's "
        + (
            "up a bit."
            if went > 0.004
            else "down a bit; not looking again till next month."
            if went < -0.004
            else "about flat."
        )
    )
    return [looked, _note(looked, words, at, 0.3)]
