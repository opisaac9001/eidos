"""The ordinary money that leaks out of a week.

Rent, food and the odd big purchase were already accounted for, which left Patrick saving
most of his wages, as if he never bought a coffee or sent his mum a card. This adds the
rest of an ordinary life: the coffee and a slice when he's at the café, a round at the
Crown, the cinema ticket, sandpaper at the hardware shop, the launderette; a weekly
scatter of bits and bobs (toothpaste, a bus fare, a haircut every couple of months); the
phone bill; cards and presents for the family's occasions; and at Christmas, the train
home and presents for everyone.

Each spend is a ``spending.made`` event that the economy turns into a transaction, so the
ledger cites what caused it. Anything he chooses to buy waits until he can afford it with
a little left over; the phone bill is owed regardless.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.application.body import body_costs
from eidos.application.economy import WEEKLY_HOUSING_PENCE, weekly_housing_pence
from eidos.application.evening_course import course_fee
from eidos.application.home_move import move_costs
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

# He won't spend on extras unless next week's rent and thirty pounds would be left, and
# below two weeks' rent the weekly bits shrink to the basics. (Shown at the first flat's rent.)
CUSHION_PENCE = 3_000
RESERVE_PENCE = WEEKLY_HOUSING_PENCE + CUSHION_PENCE
TIGHT_PENCE = 2 * WEEKLY_HOUSING_PENCE
PHONE_BILL_PENCE = 1_500
PHONE_BILL_DAY = 3
CHRISTMAS_FARE_PENCE = 6_400
CHRISTMAS_PRESENTS_PENCE = 9_500
HAIRCUT_EVERY_WEEKS = 7
HAIRCUT_PENCE = 1_400

# place -> (typical spend in pence, chance he spends anything on a visit, what on)
PLACES: dict[str, tuple[int, float, str]] = {
    "cafe": (380, 0.8, "A coffee and something at Juniper Café"),
    "bakery": (320, 0.9, "Bread and a pastry from the bakery"),
    "crown-anchor": (950, 0.9, "A couple of drinks at the Crown & Anchor"),
    "cinema": (850, 1.0, "A cinema ticket"),
    "market-hall": (900, 0.7, "Odds and ends from the market"),
    "secondhand": (400, 0.35, "Something from the secondhand shop"),
    "charity-shop": (300, 0.4, "A find at Second Chances"),
    "hardware": (650, 0.5, "Sandpaper, screws and whatever else at Foundry Hardware"),
    "pharmacy": (550, 0.8, "Bits from the pharmacy"),
    "post-office": (240, 0.5, "Stamps"),
    "launderette": (450, 1.0, "A wash and dry at the launderette"),
    "riverside-kiosk": (250, 0.8, "A tea from the kiosk"),
    "music-room": (600, 0.6, "On the door at the music room"),
    "community-hall": (400, 0.5, "Entry and a drink at the community hall"),
    "print-studio": (700, 0.6, "Studio time at the print studio"),
    "bike-repair": (1_200, 0.3, "A part from Bridge Cycles"),
    "barber": (HAIRCUT_PENCE, 1.0, "A haircut at Lane's"),
    "mill-museum": (300, 0.5, "A donation at the Mill Rooms"),
}

BITS = (
    "Bits and bobs this week: toothpaste, a bus fare, a coffee on the way somewhere",
    "The usual leak: washing-up liquid, a birthday card for someone at work, a bus fare",
    "Small stuff that adds up: batteries, bin bags, a coffee I didn't need",
    "Odds and ends: shampoo, a pint of milk twice, a paper on Saturday",
    "Everything else this week: light bulbs, a sandwich at lunch, a top-up on the bus card",
)

# occasion prefix -> (cost in pence, what he got)
GIFTS: dict[str, tuple[int, str]] = {
    "mum-birthday": (3_000, "A card and a present for Mum's birthday"),
    "dad-birthday": (3_000, "A card and a present for Dad's birthday"),
    "tom-birthday": (2_000, "A card and something daft for Tom's birthday"),
    "isla-birthday": (1_800, "A present for Isla's birthday"),
    "anniversary": (1_500, "A card for Mum and Dad's anniversary"),
    "mothering-sunday": (2_200, "Flowers for Mum on Mothering Sunday"),
    "fathers-day": (1_500, "A card and a small something for Dad on Father's Day"),
}


def spending_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    location_id: str,
    balance_pence: int,
) -> list[DomainEvent]:
    """What he spends this hour, if anything."""
    done = _recent_spends(history, at)
    rent = weekly_housing_pence(history)
    candidates = [
        *_bills(at, awake),
        *_bits(at, awake, tight=balance_pence < 2 * rent),
        *_at_place(history, at, awake, location_id),
        *_gifts(history, at),
        *_for_friends(history, at),
        *(
            (spend_id, "housing", cost, text, True)
            for spend_id, cost, text in move_costs(history, at)
        ),
        *(
            (spend_id, "everyday", cost, text, True)
            for spend_id, cost, text in course_fee(history, at)
        ),
        *(
            (spend_id, "everyday", cost, text, True)
            for spend_id, cost, text in body_costs(history, at)
        ),
        *_christmas(history, at, awake, location_id),
        *_trips_home(history, at),
    ]
    output: list[DomainEvent] = []
    available = balance_pence
    for spend_id, category, cost, text, owed in candidates:
        if spend_id in done:
            continue
        if not owed and available < cost + rent + CUSHION_PENCE:
            continue
        done.add(spend_id)
        available -= cost
        output.append(_spend(spend_id, category, cost, text, at))
    return output


def _recent_spends(history: Sequence[DomainEvent], at: datetime) -> set[str]:
    """Spends from the last few weeks: every repeatable spend's id is dated within a month."""
    since = at - timedelta(days=40)
    done: set[str] = set()
    for event in reversed(events_of(history, "spending.made")):
        raw = event.payload.get("simulated_at")
        if isinstance(raw, str) and datetime.fromisoformat(raw) < since:
            break
        done.add(str(event.payload.get("spend_id")))
    return done


_Candidate = tuple[str, str, int, str, bool]  # id, category, pence, what, owed regardless


def _bills(at: datetime, awake: bool) -> list[_Candidate]:
    if at.day != PHONE_BILL_DAY or at.hour < 9 or not awake:
        return []
    return [(f"phone-{at.year}-{at.month:02d}", "bills", PHONE_BILL_PENCE, "Phone bill", True)]


def _bits(at: datetime, awake: bool, *, tight: bool = False) -> list[_Candidate]:
    """A weekly scatter of small things, and every few weeks a haircut.

    When money is tight it's just the basics, and the haircut can wait.
    """
    if at.weekday() != 5 or at.hour < 11 or not awake:
        return []
    week = at.isocalendar()
    key = f"{week.year}-W{week.week:02d}"
    cost = 1_600 + round(2_000 * _roll("bits", key))
    text = BITS[int(_roll("bits-text", key) * len(BITS))]
    if tight:
        cost, text = cost // 2, "Just the basics this week: toothpaste and a bus fare"
    candidates: list[_Candidate] = [(f"bits-{key}", "everyday", cost, text, False)]
    if week.week % HAIRCUT_EVERY_WEEKS == 0 and not tight:
        candidates.append((f"haircut-{key}", "everyday", HAIRCUT_PENCE, "A haircut", False))
    return candidates


def _at_place(
    history: Sequence[DomainEvent], at: datetime, awake: bool, location_id: str
) -> list[_Candidate]:
    known = PLACES.get(location_id)
    if not awake or known is None:
        return []
    typical, chance, text = known
    spend_id = f"visit-{location_id}-{at.date().isoformat()}"
    if _roll(spend_id) >= chance:
        return []
    if location_id == "cafe" and _ate_at_cafe(history, at.date()):
        return []  # The meal is already paid for.
    cost = round(typical * (0.7 + 0.6 * _roll("cost", spend_id)))
    category = "everyday" if location_id in _ERRANDS else "going_out"
    return [(spend_id, category, cost, text, False)]


_ERRANDS = frozenset(
    {"bakery", "hardware", "pharmacy", "post-office", "launderette", "bike-repair", "barber"}
)


def _ate_at_cafe(history: Sequence[DomainEvent], day: date) -> bool:
    for event in reversed(events_of(history, "meal.eaten")):
        raw = event.payload.get("simulated_at")
        if not isinstance(raw, str):
            continue
        when = datetime.fromisoformat(raw).date()
        if when < day:
            return False
        if when == day and event.payload.get("provision_source") == "cafe_service":
            return True
    return False


def _gifts(history: Sequence[DomainEvent], at: datetime) -> list[_Candidate]:
    """A card and present for each family occasion he marked, late or not."""
    candidates: list[_Candidate] = []
    for event in reversed(events_of(history, "family.occasion")):
        raw = event.payload.get("simulated_at")
        if not isinstance(raw, str) or datetime.fromisoformat(raw) < at - timedelta(days=2):
            break
        occasion_id = str(event.payload.get("occasion_id", ""))
        if event.payload.get("outcome") not in {"remembered", "forgot"}:
            continue
        gift = next((g for prefix, g in GIFTS.items() if occasion_id.startswith(prefix)), None)
        if gift is None:
            continue
        cost, text = gift
        base = occasion_id.removesuffix("-late")
        candidates.append((f"gift-{base}", "gifts", cost, text, False))
    return candidates


def _for_friends(history: Sequence[DomainEvent], at: datetime) -> list[_Candidate]:
    """A present for a friend's new baby; a card and a little something when one leaves."""
    candidates: list[_Candidate] = []
    for event in reversed(events_of(history, "friend.life_event")):
        raw = event.payload.get("simulated_at")
        if not isinstance(raw, str) or datetime.fromisoformat(raw) < at - timedelta(days=2):
            break
        kind = event.payload.get("kind")
        person = str(event.payload.get("person_id"))
        if kind == "baby_born":
            candidates.append(
                (f"baby-gift-{person}", "gifts", 2_500, "A present for a friend's new baby", False)
            )
        elif kind == "moving_announced":
            candidates.append(
                (
                    f"leaving-gift-{person}",
                    "gifts",
                    1_500,
                    "A leaving card and a small present",
                    False,
                )
            )
    return candidates


def _trips_home(history: Sequence[DomainEvent], at: datetime) -> list[_Candidate]:
    """The train home for a long weekend, or in a hurry when Dad was ill."""
    candidates: list[_Candidate] = []
    for event in reversed(events_of(history, "family.plan_agreed")):
        raw = event.payload.get("simulated_at")
        if not isinstance(raw, str) or datetime.fromisoformat(raw) < at - timedelta(days=2):
            break
        plan_id = str(event.payload.get("contact_id"))
        if plan_id.startswith(("easter-", "summer-", "dad-scare-")):
            urgent = plan_id.startswith("dad-scare-")
            candidates.append(
                (f"fare-{plan_id}", "travel", CHRISTMAS_FARE_PENCE, "Train to Wye", urgent)
            )
    return candidates


def _christmas(
    history: Sequence[DomainEvent], at: datetime, awake: bool, location_id: str
) -> list[_Candidate]:
    """The train home once it's agreed, and presents bought in town before he goes."""
    if at.month != 12 or not awake:
        return []
    agreed = any(
        e.payload.get("contact_id") == f"christmas-{at.year}"
        for e in events_of(history, "family.plan_agreed")
    )
    if not agreed:
        return []
    candidates: list[_Candidate] = [
        (
            f"christmas-fare-{at.year}",
            "travel",
            CHRISTMAS_FARE_PENCE,
            "Return train to Wye for Christmas",
            False,
        )
    ]
    in_town = location_id not in {"home", "in_transit", "workshop"}
    if (at.day >= 10 and in_town and 10 <= at.hour <= 17) or at.day >= 21:
        candidates.append(
            (
                f"christmas-presents-{at.year}",
                "gifts",
                CHRISTMAS_PRESENTS_PENCE,
                "Christmas presents for Mum, Dad, Tom and Isla",
                False,
            )
        )
    return candidates


def _spend(spend_id: str, category: str, cost: int, text: str, at: datetime) -> DomainEvent:
    return DomainEvent(
        "spending.made",
        "pathos",
        {
            "spend_id": spend_id,
            "category": category,
            "cost_pence": cost,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=f"spend:{spend_id}",
    )


def spending_view(history: Sequence[DomainEvent], at: datetime) -> dict[str, int]:
    """Pence spent on each kind of thing over the last four weeks."""
    since = at - timedelta(days=28)
    totals: dict[str, int] = {}
    for event in reversed(events_of(history, "spending.made")):
        raw = event.payload.get("simulated_at")
        if not isinstance(raw, str) or datetime.fromisoformat(raw) < since:
            break
        category = str(event.payload.get("category"))
        totals[category] = totals.get(category, 0) + int(event.payload.get("cost_pence", 0))
    return totals


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


_PLAIN = {
    "everyday": "bits and bobs",
    "bills": "bills",
    "going_out": "going out",
    "gifts": "presents",
    "travel": "travel",
}


def money_context(history: Sequence[DomainEvent], at: datetime) -> dict[str, object]:
    """How money feels to him, in his terms rather than the ledger's."""
    latest = events_of(history, "finance.transaction_recorded")[-1:]
    if not latest:
        return {}
    balance = int(latest[0].payload["balance_pence"])
    weeks = balance / weekly_housing_pence(history)
    feels = "tight" if weeks < 2 else "careful" if weeks < 8 else "comfortable"
    lately = sorted(spending_view(history, at).items(), key=lambda item: -item[1])
    return {
        "how_it_feels": feels,
        "savings": f"about £{round(balance / 100, -1):.0f}",
        "where_it_goes_lately": [
            f"{_PLAIN.get(category, category)}, about £{pence / 100:.0f} in the last month"
            for category, pence in lately[:3]
        ],
    }
