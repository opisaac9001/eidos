"""Replayable nightly sleep decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold


@dataclass(frozen=True, slots=True)
class SleepWindow:
    window_id: str
    night_date: str
    selected_at: str
    bedtime: str
    wake_at: str
    reason: str

    @property
    def bed(self) -> datetime:
        return datetime.fromisoformat(self.bedtime)

    @property
    def wake(self) -> datetime:
        return datetime.fromisoformat(self.wake_at)


def project_sleep_windows(events: Sequence[DomainEvent]) -> dict[str, SleepWindow]:
    """Project one immutable sleep intention for each simulated night."""
    return dict(_WINDOWS(events))


def _windows_step(windows: dict[str, SleepWindow], event: DomainEvent) -> dict[str, SleepWindow]:
    if event.kind != "sleep.window_selected":
        return windows
    payload = event.payload
    window = SleepWindow(
        _required(payload, "window_id"),
        _required(payload, "night_date"),
        _required(payload, "selected_at"),
        _required(payload, "bedtime"),
        _required(payload, "wake_at"),
        _required(payload, "reason"),
    )
    selected, bedtime, wake = (
        datetime.fromisoformat(window.selected_at),
        window.bed,
        window.wake,
    )
    if any(value.utcoffset() is None for value in (selected, bedtime, wake)):
        raise ValueError("Sleep window times need a timezone")
    if window.night_date in windows:
        raise ValueError("A night can have only one selected sleep window")
    if selected > bedtime:
        raise ValueError("Sleep cannot be selected after its intended bedtime")
    if not timedelta(hours=5) <= wake - bedtime <= timedelta(hours=10):
        raise ValueError("A sleep window must last between five and ten hours")
    if bedtime.minute or bedtime.second or bedtime.microsecond:
        raise ValueError("Sleep bedtime must align to an hour")
    if wake.minute or wake.second or wake.microsecond:
        raise ValueError("Sleep wake time must align to an hour")
    # Copied on write: fold states are shared and must not change.
    return {**windows, window.night_date: window}


_WINDOWS: IncrementalFold[dict[str, SleepWindow]] = IncrementalFold(dict, _windows_step)


def sleep_window_at(events: Sequence[DomainEvent], at: datetime) -> SleepWindow | None:
    """Return the selected window governing this hour, including its lead-in.

    The wake hour itself still belongs to the window, so he wakes when he meant to rather
    than when an hour-of-day fallback next notices (which pushed every early morning to 7).
    """
    windows = _WINDOWS(events)
    candidates = [
        window
        for window in windows.values()
        if datetime.fromisoformat(window.selected_at) <= at <= window.wake
    ]
    return max(candidates, key=lambda item: item.selected_at, default=None)


def _required(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Sleep window requires {key}")
    return value
