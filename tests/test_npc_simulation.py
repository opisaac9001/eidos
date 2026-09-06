import unittest

from eidos.application.npc_simulation import (
    NPCDetailTier,
    nearby_npc_ids,
    npc_detail_tier,
)
from eidos.domain.world_catalog import seed_world_catalog


class NPCSimulationTests(unittest.TestCase):
    catalog = seed_world_catalog()

    def test_distance_and_attention_promote_actual_detail_tiers(self):
        self.assertEqual(
            npc_detail_tier("rowan", "park", "park", self.catalog, "rowan", frozenset())[0],
            NPCDetailTier.FOCUSED,
        )
        self.assertEqual(
            npc_detail_tier("ellis", "workshop", "park", self.catalog, None, frozenset())[0],
            NPCDetailTier.LOCAL,
        )
        self.assertEqual(
            nearby_npc_ids(
                pathos_location_id="park",
                npc_locations={"mara": "cafe", "ellis": "workshop", "rowan": "park"},
                catalog=self.catalog,
                attention_person_id="rowan",
            ),
            frozenset({"ellis", "rowan"}),
        )

    def test_active_scene_focuses_without_requiring_attention_selection(self):
        self.assertEqual(
            npc_detail_tier("rowan", "home", "home", self.catalog, None, frozenset({"rowan"}))[0],
            NPCDetailTier.FOCUSED,
        )

    def test_private_homes_are_not_pathos_home_or_local_proximity(self):
        self.assertEqual(
            npc_detail_tier("mara", "home", "home", self.catalog, "mara", frozenset())[0],
            NPCDetailTier.BACKGROUND,
        )


if __name__ == "__main__":
    unittest.main()
