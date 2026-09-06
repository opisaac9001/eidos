import json
import unittest

from eidos.adapters.british_town_signals import BritishTownSignalAdapter


class BritishTownSignalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.urls = []

        def fetch(request, timeout):
            self.urls.append(request.full_url)
            self.assertEqual(timeout, 4)
            if "open-meteo.com" in request.full_url:
                return json.dumps(
                    {
                        "utc_offset_seconds": 3600,
                        "current": {
                            "time": "2026-09-06T12:00",
                            "temperature_2m": 17.5,
                            "precipitation": 0.2,
                            "weather_code": 3,
                        },
                        "daily": {
                            "sunrise": ["2026-09-06T06:20"],
                            "sunset": ["2026-09-06T19:35"],
                        },
                    }
                ).encode()
            return b"""<rss><channel><item>
                <title>Library repair morning announced</title>
                <link>https://gazette.example/library-repair</link>
                <description>Residents can bring small household objects.</description>
                <pubDate>Sun, 06 Sep 2026 09:00:00 GMT</pubDate>
            </item></channel></rss>"""

        self.adapter = BritishTownSignalAdapter(
            "Frome",
            51.23,
            -2.32,
            news_feed_url="https://gazette.example/frome.xml",
            timeout=4,
            fetch=fetch,
        )

    def test_weather_daylight_and_news_are_attributed_and_aware(self):
        signals = self.adapter.read()
        self.assertEqual([signal.kind for signal in signals], ["weather", "daylight", "local_news"])
        self.assertTrue(all(signal.observed_at.utcoffset() is not None for signal in signals))
        self.assertEqual(signals[0].source_name, "Open-Meteo")
        self.assertEqual(signals[2].source_url, "https://gazette.example/library-repair")
        self.assertIn("timezone=Europe%2FLondon", self.urls[0])
        self.assertIn("daily=sunrise%2Csunset", self.urls[0])

    def test_unchanged_rss_item_keeps_a_stable_identity(self):
        first = self.adapter.read()[2].signal_id
        second = self.adapter.read()[2].signal_id
        self.assertEqual(first, second)

    def test_unsafe_article_link_falls_back_to_attributed_feed(self):
        def fetch(request, timeout):
            if "open-meteo.com" in request.full_url:
                return json.dumps(
                    {
                        "current": {
                            "time": "2026-09-06T12:00+00:00",
                            "temperature_2m": 12,
                            "precipitation": 0,
                            "weather_code": 1,
                        },
                        "daily": {
                            "sunrise": ["2026-09-06T06:00+00:00"],
                            "sunset": ["2026-09-06T19:00+00:00"],
                        },
                    }
                ).encode()
            return b"<rss><channel><item><title>Notice</title><link>http://unsafe.example/x</link></item></channel></rss>"

        adapter = BritishTownSignalAdapter(
            "Frome", 51.23, -2.32, news_feed_url="https://safe.example/feed", fetch=fetch
        )
        self.assertEqual(adapter.read()[2].source_url, "https://safe.example/feed")

    def test_configuration_rejects_non_british_coordinates_and_unsafe_feed(self):
        with self.assertRaises(ValueError):
            BritishTownSignalAdapter("Frome", 35, -2)
        with self.assertRaises(ValueError):
            BritishTownSignalAdapter(
                "Frome", 51.23, -2.32, news_feed_url="https://user:secret@example.test/rss"
            )


if __name__ == "__main__":
    unittest.main()
