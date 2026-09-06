import unittest
from unittest.mock import patch

from eidos.adapters.british_town_signals import BritishTownSignalAdapter
from eidos.cli import _town_source_from_env


class CliConfigurationTests(unittest.TestCase):
    def test_town_source_is_opt_in_and_requires_complete_coordinates(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(_town_source_from_env())
        with patch.dict("os.environ", {"EIDOS_TOWN_NAME": "Frome"}, clear=True):
            with self.assertRaisesRegex(ValueError, "together"):
                _town_source_from_env()

    def test_complete_town_configuration_builds_adapter(self):
        with patch.dict(
            "os.environ",
            {
                "EIDOS_TOWN_NAME": "Frome",
                "EIDOS_TOWN_LATITUDE": "51.2308",
                "EIDOS_TOWN_LONGITUDE": "-2.3201",
                "EIDOS_TOWN_NEWS_RSS_URL": "https://gazette.example/rss",
            },
            clear=True,
        ):
            source = _town_source_from_env()
        self.assertIsInstance(source, BritishTownSignalAdapter)
        self.assertEqual(source.news_feed_url, "https://gazette.example/rss")


if __name__ == "__main__":
    unittest.main()
