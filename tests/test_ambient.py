import json
import unittest

from eidos.domain.ambient import (
    ambient_output_schema,
    parse_ambient_candidate,
    validate_ambient_candidate,
)
from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected


class AmbientCandidateTests(unittest.TestCase):
    def candidate(self, **changes):
        raw = {
            "event_type": "unexpected_violinist",
            "description": "A traveling violinist begins tuning beneath the old park clock.",
            "location_id": "park",
            "cause": "the station waiting room has closed",
            "theme": "hospitality",
            "opportunity": "stop and listen",
            "participation": "A passerby may listen, speak with the player, or continue walking.",
            "stakes": "A brief connection or a missed ordinary encounter.",
            "resource_id": "community-sketch-basket",
            "starts_in_hours": 3,
            "intensity": 0.3,
            "duration_hours": 4,
        }
        raw.update(changes)
        return parse_ambient_candidate(json.dumps(raw))

    def test_event_type_is_open_ended_but_shape_is_strict(self):
        candidate = self.candidate(event_type="a_category_never_seen_before")
        self.assertEqual(candidate.event_type, "a_category_never_seen_before")
        validate_ambient_candidate(
            candidate,
            known_locations={"park"},
            known_resources={"community-sketch-basket": "park"},
            history=[],
        )
        with self.assertRaises(ProposalRejected):
            parse_ambient_candidate(json.dumps({"description": "missing everything else"}))

    def test_grounding_and_recent_novelty_are_required(self):
        with self.assertRaisesRegex(ProposalRejected, "unknown place"):
            validate_ambient_candidate(
                self.candidate(location_id="moon"),
                known_locations={"park"},
                known_resources={"community-sketch-basket": "park"},
                history=[],
            )
        with self.assertRaisesRegex(ProposalRejected, "not at the proposed place"):
            validate_ambient_candidate(
                self.candidate(),
                known_locations={"park"},
                known_resources={"community-sketch-basket": "cafe"},
                history=[],
            )
        previous = DomainEvent(
            "world_event.accepted",
            "pathos",
            {
                "event_kind": "ambient",
                "description": "A traveling violinist begins tuning beneath the old park clock.",
            },
        )
        with self.assertRaisesRegex(ProposalRejected, "repeats recent"):
            validate_ambient_candidate(
                self.candidate(),
                known_locations={"park"},
                known_resources={"community-sketch-basket": "park"},
                history=[previous],
            )

    def test_schema_requires_every_field_without_enumerating_event_types(self):
        schema = ambient_output_schema()
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        self.assertNotIn("enum", schema["properties"]["event_type"])
        self.assertFalse(schema["additionalProperties"])
        expanded = ambient_output_schema(
            ("park", "old-glasshouse"), ("community-sketch-basket", "glasshouse-tools")
        )
        self.assertEqual(
            expanded["properties"]["location_id"]["enum"],
            ["park", "old-glasshouse"],
        )
        self.assertEqual(
            expanded["properties"]["resource_id"]["enum"],
            ["community-sketch-basket", "glasshouse-tools"],
        )

    def test_novelty_score_compares_open_metadata_not_only_exact_description(self):
        accepted = DomainEvent(
            "world_event.accepted",
            "pathos",
            {
                "proposal_id": "prior",
                "event_kind": "ambient",
                "description": "A violinist shares a short tune near the old park clock.",
            },
        )
        linked = DomainEvent(
            "world_event.theme_linked",
            "pathos",
            {
                "proposal_id": "prior",
                "event_type": "unexpected_violinist",
                "theme": "hospitality",
                "opportunity": "stop and listen",
            },
        )
        novelty = validate_ambient_candidate(
            self.candidate(
                description="A traveling violinist tunes below the clock while people cross the park."
            ),
            known_locations={"park"},
            known_resources={"community-sketch-basket": "park"},
            history=[accepted, linked],
        )
        self.assertGreater(novelty, 0.35)
        self.assertLess(novelty, 1.0)


if __name__ == "__main__":
    unittest.main()
