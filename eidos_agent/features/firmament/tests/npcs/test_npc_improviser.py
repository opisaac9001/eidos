# eidos_agent/features/firmament/tests/npcs/test_npc_improviser.py

import unittest
from unittest.mock import patch, MagicMock # Added MagicMock
import logging # For capturing log output
from typing import Dict, Any # For type hints if needed

# Adjust import path based on actual file structure
try:
    # Assuming tests are run from project root where eidos_agent is a top-level package
    from eidos_agent.features.firmament.npcs.npc_improviser import NPCImproviser
    from eidos_agent.core.config import Config, LLMConfig # For mocking
except ImportError: # pragma: no cover
    print("Could not resolve imports for NPCImproviser test. Using dummy classes.")
    LLMConfig = Dict[str, Any] #type:ignore
    class NPCImproviser: #type:ignore
        def __init__(self, firmament_llm_role_name=None):
            self.llm_role_name = firmament_llm_role_name if firmament_llm_role_name else "dummy_role"
            self.llm_config = {"model":"dummy_model_from_improviser_dummy", "url": "http://dummy_url"} if self.llm_role_name != "A_ROLE_WITH_NO_CONFIG" else None
            print(f"Dummy NPCImproviser initialized with role {self.llm_role_name} and config {self.llm_config}")
        def _build_improvisation_prompt(self, nh, sct, sc): return "dummy prompt"
        def improvise_npc(self, name_hint=None, subconscious_thought_context=None, scene_context=None):
            if not self.llm_config: return None
            return {"id": "dummy_id", "name": name_hint or "Dummy NPC", "appearance": "dummied", "role": "tester",
                    "personality": "testy", "relationship_to_pathos": "test subject", "initial_dialogue": "Testing..."}
    class Config: #type:ignore
        @staticmethod
        def get_firmament_module_config(): return {"firmament_llm_role": "TEST_FIRMAMENT_IMPROVISER_ROLE"}
        @staticmethod
        def get_llm_config(role_name):
            if role_name == "TEST_FIRMAMENT_IMPROVISER_ROLE":
                return {"role": role_name, "model": "test_improviser_model_from_config_dummy", "url": "http://testurl"}
            return None

# It's often good practice to disable or lower the log level of the module under test
# during unit tests, unless specifically testing log output.
# However, for the prompt logging test, we need INFO.
# logging.getLogger('eidos_agent.features.firmament.npcs.npc_improviser').setLevel(logging.WARNING)


class TestNPCImproviser(unittest.TestCase):

    def setUp(self):
        # This mock setup will apply to all tests in this class for Config methods
        # We patch 'eidos_agent.core.config.Config' because that's where it's defined.
        # If NPCImproviser imports it as `from ....core.config import Config`, this path is correct.
        self.mock_fm_config_patcher = patch('eidos_agent.features.firmament.npcs.npc_improviser.Config.get_firmament_module_config')
        self.mock_llm_config_patcher = patch('eidos_agent.features.firmament.npcs.npc_improviser.Config.get_llm_config')

        self.mock_get_fm_config = self.mock_fm_config_patcher.start()
        self.mock_get_llm_config = self.mock_llm_config_patcher.start()

        self.test_llm_role = "TEST_IMPROVISER_ROLE_SETUP"
        self.test_llm_model = "test_improviser_model_v_setup"

        self.mock_get_fm_config.return_value = {"firmament_llm_role": self.test_llm_role}
        self.mock_get_llm_config.return_value = {
            "role": self.test_llm_role, "model": self.test_llm_model,
            "url": "http://test_improviser_url_setup"
        }
        # Create a new improviser for each test to ensure isolation
        self.improviser = NPCImproviser(firmament_llm_role_name=self.test_llm_role)

    def tearDown(self):
        self.mock_fm_config_patcher.stop()
        self.mock_llm_config_patcher.stop()

    def test_npc_improviser_initialization_with_specific_role(self):
        print("Running: test_npc_improviser_initialization_with_specific_role")
        # Config mocks are already set up by setUp to return values for self.test_llm_role

        # Re-asserting what setUp should have done with a specific role passed to constructor
        self.mock_get_fm_config.assert_not_called() # Should not be called if role_name is passed to __init__
        self.mock_get_llm_config.assert_called_with(self.test_llm_role)
        self.assertEqual(self.improviser.llm_role_name, self.test_llm_role)
        self.assertIsNotNone(self.improviser.llm_config)
        if self.improviser.llm_config: # For type checker
            self.assertEqual(self.improviser.llm_config.get("model"), self.test_llm_model)
        print("Test Passed: NPCImproviser initialized correctly with specific role and mocked config.")

    def test_npc_improviser_initialization_uses_default_role_from_config(self):
        print("Running: test_npc_improviser_initialization_uses_default_role_from_config")
        # Reset mocks to check calls for this specific scenario
        self.mock_get_fm_config.reset_mock()
        self.mock_get_llm_config.reset_mock()

        default_role_from_fm_config = "DEFAULT_FIRMAMENT_ROLE_FROM_CFG"
        default_model_for_that_role = "default_cfg_model"
        self.mock_get_fm_config.return_value = {"firmament_llm_role": default_role_from_fm_config}
        self.mock_get_llm_config.return_value = {"role": default_role_from_fm_config, "model": default_model_for_that_role, "url": "http://default_url"}

        improviser_default = NPCImproviser() # No role passed, should use default from fm_config

        self.mock_get_fm_config.assert_called_once()
        self.mock_get_llm_config.assert_called_once_with(default_role_from_fm_config)
        self.assertEqual(improviser_default.llm_role_name, default_role_from_fm_config)
        self.assertIsNotNone(improviser_default.llm_config)
        if improviser_default.llm_config: # For type checker
            self.assertEqual(improviser_default.llm_config.get("model"), default_model_for_that_role)
        print("Test Passed: NPCImproviser initialized correctly using default role from Firmament config.")


    @patch('eidos_agent.features.firmament.npcs.npc_improviser.logger.info')
    @patch('eidos_agent.features.firmament.npcs.npc_improviser.logger.debug')
    def test_improvise_npc_prompt_generation_and_hardcoded_response(self, mock_logger_debug, mock_logger_info):
        print("Running: test_improvise_npc_prompt_generation_and_hardcoded_response")
        name_hint = "Cassidy"
        subconscious_context = "Pathos feels like he's being watched from the shadows."
        scene_context = {
            "location_description": "a dimly lit, narrow alleyway with overflowing bins",
            "pathos_mood_state": "uneasy and suspicious",
            "current_activity_name": "walking home late after a strange encounter",
            "time_of_day": "past midnight, moonless night",
            "recent_world_events_summary": "Reports of unusual activity in the neighborhood lately.",
            "pathos_current_intention": "Get home quickly and safely."
        }

        npc_profile = self.improviser.improvise_npc(name_hint, subconscious_context, scene_context)

        # Check that the detailed prompt was logged via logger.debug
        prompt_logged_debug = False
        full_logged_prompt = ""
        for call_args in mock_logger_debug.call_args_list:
            args, _ = call_args
            if args and "Full prompt that WOULD be sent to LLM" in args[0]:
                full_logged_prompt = args[0]
                self.assertIn(name_hint, full_logged_prompt)
                self.assertIn(subconscious_context, full_logged_prompt)
                self.assertIn(scene_context["location_description"], full_logged_prompt)
                self.assertIn(scene_context["pathos_mood_state"], full_logged_prompt)
                self.assertIn(scene_context["current_activity_name"], full_logged_prompt)
                self.assertIn(scene_context["time_of_day"], full_logged_prompt)
                self.assertIn(scene_context["recent_world_events_summary"], full_logged_prompt)
                self.assertIn(scene_context["pathos_current_intention"], full_logged_prompt)
                prompt_logged_debug = True
                break
        self.assertTrue(prompt_logged_debug, "The detailed improvisation prompt was not logged via logger.debug as expected.")

        # Check that the INFO log about SIMULATING LLM call contains role and model
        sim_call_logged_info = False
        for call_args in mock_logger_info.call_args_list:
            args, _ = call_args
            if args and "SIMULATING LLM call for NPC improvisation" in args[0]:
                self.assertIn(f"Role: '{self.test_llm_role}'", args[0])
                self.assertIn(f"Model: '{self.test_llm_model}'", args[0])
                sim_call_logged_info = True
                break
        self.assertTrue(sim_call_logged_info, "The INFO log for simulated LLM call was not found or missing details.")


        # Check the hardcoded response structure
        self.assertIsNotNone(npc_profile)
        self.assertEqual(npc_profile.get("name"), name_hint)
        self.assertIn("appearance", npc_profile)
        self.assertTrue(npc_profile.get("appearance", "").endswith("(simulated)"))
        self.assertIn("role", npc_profile)
        self.assertIn("personality", npc_profile)
        self.assertIn("relationship_to_pathos", npc_profile)
        self.assertIn("initial_dialogue", npc_profile)
        # Check that all values are strings for the hardcoded generic response
        if npc_profile.get("name") == name_hint: # i.e., not the "Lara" special case
            self.assertTrue(all(isinstance(v, str) for k, v in npc_profile.items() if k != 'id' or isinstance(v, str))), # id might not be string if dummy is used
                        "Not all profile values were strings in the generic hardcoded response.")
        print("Test Passed: Prompt logged (simulated) and hardcoded NPC profile returned with expected structure.")

    def test_improvise_npc_lara_specific_hardcoded_case(self):
        print("Running: test_improvise_npc_lara_specific_hardcoded_case")
        name_hint = "Lara"
        scene_context = {"location_description": "a cafe"}

        npc_profile = self.improviser.improvise_npc(name_hint=name_hint, scene_context=scene_context)

        self.assertIsNotNone(npc_profile)
        self.assertTrue(npc_profile.get("name", "").startswith("Lara")) # Name might be "Lara (Improvised)" or "Lara Miller" etc.
        self.assertIn("sharp jaw", npc_profile.get("appearance", ""))
        self.assertEqual(npc_profile.get("role"), "Barista at a nearby, slightly grungy but popular coffee spot (simulated)")
        self.assertTrue(npc_profile.get("initial_dialogue", "").endswith("(simulated)"))
        print("Test Passed: Lara-specific hardcoded case returned correctly.")

    def test_improvise_npc_no_name_hint_generic_hardcoded_case(self):
        print("Running: test_improvise_npc_no_name_hint_generic_hardcoded_case")
        scene_context = {"location_description": "a library"}

        npc_profile = self.improviser.improvise_npc(scene_context=scene_context)

        self.assertIsNotNone(npc_profile)
        self.assertTrue(npc_profile.get("name", "").startswith("Generated NPC"))
        self.assertIn("(simulated)", npc_profile.get("appearance", ""))
        self.assertIn("(simulated)", npc_profile.get("role", ""))
        print("Test Passed: No-name-hint generic hardcoded case returned correctly.")

    @patch('eidos_agent.features.firmament.npcs.npc_improviser.Config.get_llm_config', return_value=None)
    @patch('eidos_agent.features.firmament.npcs.npc_improviser.Config.get_firmament_module_config')
    def test_improvise_npc_no_llm_config_logs_error_and_returns_none(self, mock_get_fm_config_inner, mock_get_llm_config_inner_none):
        print("Running: test_improvise_npc_no_llm_config_logs_error_and_returns_none")

        # Setup Config mocks for this specific test case
        no_config_role = "A_ROLE_WITH_NO_CONFIG_DEFINED"
        mock_get_fm_config_inner.return_value = {"firmament_llm_role": no_config_role}
        # mock_get_llm_config_inner_none is already patched to return None by decorator

        # Re-initialize improviser with this setup so it attempts to load the non-existent config
        with self.assertLogs(logger='eidos_agent.features.firmament.npcs.npc_improviser', level='ERROR') as log_cm:
            improviser_no_config = NPCImproviser(firmament_llm_role_name=no_config_role)
            self.assertTrue(any(f"LLM configuration for role '{no_config_role}' not found" in record.getMessage() for record in log_cm.records))

        self.assertIsNone(improviser_no_config.llm_config)

        # Now, try to improvise, it should log another error and return None
        with self.assertLogs(logger='eidos_agent.features.firmament.npcs.npc_improviser', level='ERROR') as log_cm_improvise:
            npc_profile = improviser_no_config.improvise_npc(scene_context={})
            self.assertTrue(any(f"Cannot improvise NPC, LLM configuration is missing for role '{no_config_role}'" in record.getMessage() for record in log_cm_improvise.records))

        self.assertIsNone(npc_profile, "Should return None if LLM config is missing during improvisation.")
        print("Test Passed: Returns None and logs error if LLM config is missing.")


if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.DEBUG) # Enable DEBUG to see the full prompt logs from improviser
    unittest.main(verbosity=2)
