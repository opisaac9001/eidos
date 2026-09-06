"""Opt-in weather/daylight and RSS signals for one configured British town."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Callable, cast
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from eidos.ports.town_signals import TownSignal

Fetch = Callable[[Request, float], bytes]


class BritishTownSignalAdapter:
    def __init__(
        self,
        town: str,
        latitude: float,
        longitude: float,
        *,
        news_feed_url: str | None = None,
        timeout: float = 15,
        fetch: Fetch | None = None,
    ) -> None:
        if not town.strip() or not 49 <= latitude <= 61 or not -9 <= longitude <= 3:
            raise ValueError("British town configuration is invalid")
        if news_feed_url is not None:
            parsed = urlsplit(news_feed_url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Town news feed must be a credential-free HTTPS URL")
        self.town = town.strip()
        self.latitude = latitude
        self.longitude = longitude
        self.news_feed_url = news_feed_url
        self.timeout = timeout
        self.fetch = fetch or _fetch

    def read(self) -> list[TownSignal]:
        output = self._weather_and_daylight()
        if self.news_feed_url is not None:
            output.extend(self._news())
        return output

    def _weather_and_daylight(self) -> list[TownSignal]:
        query = urlencode(
            {
                "latitude": self.latitude,
                "longitude": self.longitude,
                "current": "temperature_2m,precipitation,weather_code",
                "daily": "sunrise,sunset",
                "timezone": "Europe/London",
                "forecast_days": 1,
            }
        )
        source_url = f"https://api.open-meteo.com/v1/forecast?{query}"
        raw = json.loads(
            self.fetch(Request(source_url, headers={"User-Agent": "Eidos/0.1"}), self.timeout)
        )
        current, daily = raw["current"], raw["daily"]
        observed = _aware(str(current["time"]), raw.get("utc_offset_seconds", 0))
        sunrise = _aware(str(daily["sunrise"][0]), raw.get("utc_offset_seconds", 0))
        sunset = _aware(str(daily["sunset"][0]), raw.get("utc_offset_seconds", 0))
        weather = (
            f"Weather code {int(current['weather_code'])}; {float(current['temperature_2m']):.1f}°C; "
            f"{float(current['precipitation']):.1f} mm recent precipitation."
        )
        return [
            self._signal("weather", "Current weather", weather, observed, source_url),
            self._signal(
                "daylight",
                "Today’s daylight",
                f"Sunrise {sunrise.isoformat()}; sunset {sunset.isoformat()}.",
                observed,
                source_url,
            ),
        ]

    def _news(self) -> list[TownSignal]:
        assert self.news_feed_url is not None
        body = self.fetch(
            Request(self.news_feed_url, headers={"User-Agent": "Eidos/0.1"}), self.timeout
        )
        root = ET.fromstring(body)
        output: list[TownSignal] = []
        for item in root.findall(".//item")[:5]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            parsed_link = urlsplit(link)
            source_url = (
                link
                if parsed_link.scheme == "https"
                and parsed_link.hostname
                and not parsed_link.username
                and not parsed_link.password
                else self.news_feed_url
            )
            description = " ".join((item.findtext("description") or "").split())[:300] or title
            published = (item.findtext("pubDate") or "").strip()
            if not title:
                continue
            observed = datetime.now(timezone.utc)
            stable_key = published or link or f"{title}|{description}"
            output.append(
                self._signal(
                    "local_news",
                    title,
                    description,
                    observed,
                    source_url,
                    stable_key,
                    stable=True,
                )
            )
        return output

    def _signal(
        self,
        kind: str,
        title: str,
        summary: str,
        observed_at: datetime,
        source_url: str,
        salt: str = "",
        *,
        stable: bool = False,
    ) -> TownSignal:
        timestamp = "" if stable else observed_at.isoformat()
        key = f"{kind}|{self.town}|{title}|{summary}|{timestamp}|{salt}"
        return TownSignal(
            sha256(key.encode()).hexdigest()[:24],
            kind,
            self.town,
            title,
            summary,
            observed_at,
            "Open-Meteo" if kind != "local_news" else urlsplit(source_url).hostname or "RSS",
            source_url,
        )


def _fetch(request: Request, timeout: float) -> bytes:
    with urlopen(request, timeout=timeout) as response:
        body = cast(bytes, response.read(1_000_001))
    if len(body) > 1_000_000:
        raise ValueError("Town signal response exceeds size limit")
    return body


def _aware(value: str, offset_seconds: object) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        return parsed
    if isinstance(offset_seconds, bool) or not isinstance(offset_seconds, (int, float)):
        raise ValueError("Town signal timezone offset is invalid")
    return parsed.replace(tzinfo=timezone(timedelta(seconds=float(offset_seconds))))
