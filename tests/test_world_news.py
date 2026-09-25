"""Real news reaches him, he has a take, it touches his life, and he can talk about it."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from eidos.adapters.news_feeds import RssNewsAdapter
from eidos.adapters.standin_gateway import StandInGateway, _standin_news_reply
from eidos.application.town_signals import real_weather
from eidos.application.world_news import (
    _valid,
    news_context,
    news_events,
    news_on_his_mind,
    price_pressure,
)
from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected

TODAY = datetime(2026, 9, 25, 7, tzinfo=timezone.utc)

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>BBC News</title>
<item><title><![CDATA[Energy bills to rise again this winter]]></title>
<description><![CDATA[The price cap goes up by 6% from January, the regulator says.]]></description>
<link>https://www.bbc.co.uk/news/articles/a1?at_medium=RSS</link>
<pubDate>Fri, 25 Sep 2026 05:00:00 GMT</pubDate></item>
<item><title>Watch: a video you can't read</title><link>https://www.bbc.co.uk/v</link></item>
<item><title><![CDATA[Rapid new test cuts brain tumour diagnosis to hours]]></title>
<description><![CDATA[Patients can start treatment sooner.]]></description>
<link>https://www.bbc.co.uk/news/articles/a2</link>
<pubDate>Fri, 25 Sep 2026 04:00:00 GMT</pubDate></item>
</channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Other</title>
<entry><title>Rail strike called for next weekend</title><summary>Trains across the south
will be cancelled on Saturday.</summary><link href="https://example.org/strike"/>
<updated>2026-09-25T06:00:00Z</updated></entry></feed>"""


def adapter() -> RssNewsAdapter:
    pages = {"https://f/rss": RSS, "https://f/atom": ATOM}
    return RssNewsAdapter(
        (("top", "https://f/rss"), ("uk", "https://f/atom")),
        fetch=lambda request, timeout: pages[request.full_url],
    )


def test_feeds_are_read_as_stories_without_video_pages() -> None:
    stories = adapter().read()
    headlines = [s.headline for s in stories]
    assert "Energy bills to rise again this winter" in headlines
    assert "Rail strike called for next weekend" in headlines
    assert not any(h.startswith("Watch") for h in headlines)
    assert all(s.source_url.startswith("https://") for s in stories)
    with pytest.raises(ValueError):
        RssNewsAdapter((("top", "http://insecure"),))


def read(at=TODAY, now=TODAY, history=()):
    return asyncio.run(
        news_events(
            list(history),
            at,
            adapter(),
            StandInGateway(),
            awake=True,
            identity={"values": {"care": 0.78}},
            now=lambda: now,
        )
    )


def test_morning_news_is_heard_and_he_has_a_take() -> None:
    events = read()
    heard = [e for e in events if e.kind == "news.heard"]
    takes = [e for e in events if e.kind == "news.take"]
    assert len(heard) == 3 and takes
    bills = next(e for e in takes if "Energy" in e.payload["headline"])
    assert bills.payload["touches_his_life"] == "prices" and bills.payload["feeling"] < 0
    assert all(e.payload["real_world"] for e in heard)
    # Already seen: nothing new that evening.
    evening = read(TODAY.replace(hour=18), history=events)
    assert not [e for e in evening if e.kind == "news.heard"]


def test_no_real_news_in_a_simulation_that_isnt_today() -> None:
    assert read(at=TODAY + timedelta(days=400)) == []
    assert read(at=TODAY.replace(hour=11)) == []


def test_takes_must_be_about_stories_he_saw_and_claim_nothing() -> None:
    heard = {"s1": DomainEvent("news.heard", "pathos", {"headline": "x"})}
    good = {
        "story_id": "s1",
        "take": "Grim. Read it twice.",
        "feeling": -2,
        "salience": 0.5,
        "touches_his_life": "nonsense",
    }
    story_id, _, feeling, _, touches = _valid(good, heard)
    assert feeling == -1.0 and touches == "none"
    with pytest.raises(ProposalRejected):
        _valid({**good, "story_id": "invented"}, heard)
    with pytest.raises(ProposalRejected):
        _valid({**good, "take": "I was there when it happened."}, heard)


def test_the_news_touches_his_life_and_his_conversation() -> None:
    events = read()
    at = TODAY + timedelta(hours=3)
    assert price_pressure(events, at) == pytest.approx(1.1)
    assert price_pressure(events, at + timedelta(days=40)) == 1.0
    assert news_on_his_mind(events, at)
    context = news_context(events, at)
    assert context["in_the_news"] and "news_instruction" in context
    reply = _standin_news_reply("did you see the energy bills are going up again", context)
    assert reply and "saw that" in reply
    assert _standin_news_reply("did you hear about the moon landing", context) == (
        "I haven't seen that, actually. What happened?"
    )


def test_the_real_sky_is_his_sky_when_his_day_is_today() -> None:
    observed = DomainEvent(
        "external_signal.observed",
        "pathos",
        {
            "signal_kind": "weather",
            "summary": "Weather code 61; 12.0°C; 1.2 mm recent precipitation.",
            "external_observed_at": TODAY.isoformat(),
        },
    )
    assert real_weather([observed], TODAY, TODAY) == "Light rain"
    assert real_weather([observed], TODAY + timedelta(days=30), TODAY) is None
    stale = TODAY + timedelta(hours=20)
    assert real_weather([observed], stale, stale) is None


def test_a_live_world_hears_todays_news_whatever_its_calendar_says() -> None:
    january = datetime(2026, 1, 8, 7, tzinfo=timezone.utc)
    assert read(at=january) == []
    live = asyncio.run(
        news_events(
            [],
            january,
            adapter(),
            StandInGateway(),
            awake=True,
            identity={},
            now=lambda: TODAY,
            live=True,
        )
    )
    assert [e for e in live if e.kind == "news.heard"]
