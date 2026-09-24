"""Remember perceived possibilities without manufacturing plans or hidden knowledge."""

from collections.abc import Hashable
from datetime import datetime, timedelta
from typing import NamedTuple, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import GrowOnlyMap, IncrementalFold, events_of


class _Unnoticed(NamedTuple):
    # Every ``source_perception_id`` noticed so far, and the pathos perceptions offering a
    # possibility whose id is not (yet) among them, in history order.
    sources: GrowOnlyMap[Hashable, bool]
    perceptions: tuple[DomainEvent, ...]


def _unnoticed_step(state: _Unnoticed, event: DomainEvent) -> _Unnoticed:
    if event.kind == "opportunity.noticed":
        sources = state.sources.with_item(event.payload.get("source_perception_id"), True)
        return _Unnoticed(
            sources,
            tuple(item for item in state.perceptions if str(item.event_id) not in sources),
        )
    if event.kind != "perception.recorded" or event.payload.get("owner") != "pathos":
        return state
    text = event.payload.get("opportunity")
    if str(event.event_id) in state.sources or not isinstance(text, str) or not text.strip():
        return state
    return _Unnoticed(state.sources, (*state.perceptions, event))


_UNNOTICED: IncrementalFold[_Unnoticed] = IncrementalFold(
    lambda: _Unnoticed(GrowOnlyMap(), ()), _unnoticed_step
)


def opportunity_events(history: Sequence[DomainEvent], now: datetime) -> list[DomainEvent]:
    if now.utcoffset() is None:
        raise ValueError("Opportunity time must be timezone-aware")
    # Exactly the perceptions a scan of history against all noticed sources would keep.
    sources: set[str] = set()
    output = []
    for event in _UNNOTICED(history).perceptions:
        source_id = str(event.event_id)
        text = event.payload.get("opportunity")
        if source_id in sources or not isinstance(text, str) or not text.strip():
            continue
        try:
            observed = datetime.fromisoformat(str(event.payload.get("simulated_at")))
        except ValueError:
            continue
        if observed.utcoffset() is None or observed > now:
            continue
        duration = event.payload.get("duration_hours")
        expires = (
            (observed + timedelta(hours=duration)).isoformat()
            if (
                isinstance(duration, (int, float))
                and not isinstance(duration, bool)
                and 0 < duration <= 24
            )
            else None
        )
        output.append(
            DomainEvent(
                "opportunity.noticed",
                "pathos",
                {
                    "opportunity_id": f"opportunity-{source_id}",
                    "source_perception_id": source_id,
                    "text": text.strip()[:500],
                    "location_id": event.payload.get("location_id"),
                    "resource_id": event.payload.get("resource_id"),
                    "owner": "pathos",
                    "expires_at": expires,
                    "action_authority": False,
                    "simulated_at": now.isoformat(),
                },
                causation_id=event.event_id,
                correlation_id=event.correlation_id,
            )
        )
        sources.add(source_id)
    return output


def available_opportunities(
    history: Sequence[DomainEvent], now: datetime
) -> list[dict[str, object]]:
    """Read-only context; unknown/expired possibilities never become appointments."""
    closed = {
        event.payload.get("opportunity_id")
        for event in events_of(history, "opportunity.closed")
        if event.payload.get("owner") == "pathos"
    }
    result = []
    for event in events_of(history, "opportunity.noticed"):
        if event.payload.get("owner") != "pathos":
            continue
        if event.payload.get("opportunity_id") in closed:
            continue
        expires = event.payload.get("expires_at")
        if isinstance(expires, str) and datetime.fromisoformat(expires) <= now:
            continue
        result.append({**event.payload, "action_authority": False})
    return result[-12:]
