"""Remember perceived possibilities without manufacturing plans or hidden knowledge."""

from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent


def opportunity_events(history: Sequence[DomainEvent], now: datetime) -> list[DomainEvent]:
    if now.utcoffset() is None:
        raise ValueError("Opportunity time must be timezone-aware")
    sources = {
        event.payload.get("source_perception_id")
        for event in history
        if event.kind == "opportunity.noticed"
    }
    output = []
    for event in history:
        if event.kind != "perception.recorded" or event.payload.get("owner") != "pathos":
            continue
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
        for event in history
        if event.kind == "opportunity.closed" and event.payload.get("owner") == "pathos"
    }
    result = []
    for event in history:
        if event.kind != "opportunity.noticed" or event.payload.get("owner") != "pathos":
            continue
        if event.payload.get("opportunity_id") in closed:
            continue
        expires = event.payload.get("expires_at")
        if isinstance(expires, str) and datetime.fromisoformat(expires) <= now:
            continue
        result.append({**event.payload, "action_authority": False})
    return result[-12:]
