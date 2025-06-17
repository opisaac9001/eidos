# eidos_agent/features/firmament/tests/npcs/test_npc_improviser.py

import unittest
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
import logging
import json
import asyncio
from typing import Dict, Any, AsyncGenerator, Optional, List # Added Optional, List

# Adjust import path based on actual file structure
try:
    from eidos_agent.features.firmament.npcs.npc_improviser import NPCImproviser
    from eidos_agent.core.config import Config, LLMConfig
    from eidos_agent.llm_integrations.llm_client import LLMClient # For type hinting mock
except ImportError: # pragma: no cover
    print("CRITICAL: NPCImproviser test imports failed. Using dummies.")
    LLMConfig = Dict[str, Any]; #type:ignore
    class NPCImproviser: #type:ignore
        def __init__(self,r=None):
            self.llm_role_name="dummy_role_in_dummy_improviser"
            self.llm_config: Optional[LLMConfig] = {"model":"dummy_model_in_dummy_improviser", "url":"http://dummyurl", "timeout": 5.0} if r != "A_ROLE_WITH_NO_CONFIG_DEFINED" else None
        def _build_improvisation_prompt(self, nh, sct, sc): return "dummy_prompt_content"
        async def improvise_npc(s,nh=None,sct=None,sc=None):
            if not s.llm_config: return None
            return {"name":nh or "DummyNPCFromDummyImproviser","id":"d1_dummy_improv"}
    class Config: #type:ignore
        @staticmethod
        def get_firmament_module_config(): return {"firmament_llm_role":"DUMMY_FIRMAMENT_TEST_ROLE"}
        @staticmethod
        def get_llm_config(role_name_arg):
            if role_name_arg=="DUMMY_FIRMAMENT_TEST_ROLE": return {"role":role_name_arg,"model":"dummy_model_from_config","url":"http://dummy_cfg_url"}
            if role_name_arg=="A_ROLE_WITH_NO_CONFIG_DEFINED": return None
            return {"role":role_name_arg,"model":"generic_dummy_model","url":"http://generic_dummy_url"}

    class LLMClient: pass #type:ignore

# This mock async generator will be the return_value for the patched LLMClient.call_llm_api
async def mock_llm_api_response_generator(
    response_data: Any,
    is_error_chunk: bool = False,
    is_malformed_json_string: bool = False,
    is_incomplete_json_string: bool = False,
    is_empty_string: bool = False
) -> AsyncGenerator[Any, None]:
    # logger_mock_gen = logging.getLogger("MockLLMGenerator") # For debugging the generator itself
    # logger_mock_gen.debug(f"MockLLMGenerator called with: data='{str(response_data)[:50]}...', error_chunk={is_error_chunk}, malformed={is_malformed_json_string}, incomplete={is_incomplete_json_string}, empty={is_empty_string}")
    if is_error_chunk:
        # logger_mock_gen.debug("Yielding error chunk.")
        yield {"type": "error_chunk", "payload": response_data} # response_data is the error message string
    elif is_malformed_json_string:
        # logger_mock_gen.debug("Yielding malformed JSON string.")
        yield "This is { not valid json"
    elif is_incomplete_json_string:
        # logger_mock_gen.debug("Yielding incomplete JSON string (missing required fields).")
        yield json.dumps({"name": "Incomplete NPC", "id": "inc_123"}) # Missing appearance, role etc.
    elif is_empty_string:
        # logger_mock_gen.debug("Yielding empty string.")
        yield ""
    elif isinstance(response_data, str): # This should be a valid JSON string
        # logger_mock_gen.debug(f"Yielding JSON string: {response_data}")
        yield response_data
    else: # Should not happen if test provides string for success
        # logger_mock_gen.error(f"MockLLMGenerator: Unexpected response_data type: {type(response_data)}")
        yield {"type": "error_chunk", "payload": "Mock generator misconfigured"}


# For Python versions < 3.8, IsolatedAsyncioTestCase might not be available.
# Using unittest.TestCase and asyncio.run() for broader compatibility if needed.
# However, modern unittest typically handles `async def` test methods correctly.
class TestNPCImproviser(unittest.TestCase):

    def setUp(self):
        # Patch Config methods used by NPCImproviser's __init__
        # The target for patch should be where the Config class is *looked up* by npc_improviser.py
        self.mock_fm_config_patcher = patch('eidos_agent.features.firmament.npcs.npc_improviser.Config.get_firmament_module_config')
        self.mock_llm_config_patcher = patch('eidos_agent.features.firmament.npcs.npc_improviser.Config.get_llm_config')

        self.mock_get_fm_config = self.mock_fm_config_patcher.start()
        self.mock_get_llm_config = self.mock_llm_config_patcher.start()

        self.test_llm_role = "TEST_IMPROVISER_ASYNC_ROLE"
        self.test_llm_model = "test_improviser_async_model_v2"
        self.test_llm_url = "http://test_async_url_v2"
        self.mock_llm_config_dict: LLMConfig = { # type: ignore
            "role": self.test_llm_role, "model": self.test_llm_model,
            "url": self.test_llm_url, "timeout": 10.0, "temperature": 0.7, "max_tokens": 500
        }
        # Default mock returns for successful config loading in __init__
        self.mock_get_fm_config.return_value = {"firmament_llm_role": self.test_llm_role}
        self.mock_get_llm_config.return_value = self.mock_llm_config_dict

        self.improviser = NPCImproviser(firmament_llm_role_name=self.test_llm_role)

    def tearDown(self):
        self.mock_fm_config_patcher.stop()
        self.mock_llm_config_patcher.stop()

    def test_npc_improviser_initialization(self):
        print("Running: test_npc_improviser_initialization (async context)")
        # This test now verifies the state set by setUp's default mocks
        self.mock_get_fm_config.assert_not_called() # Because role_name was passed to __init__
        self.mock_get_llm_config.assert_called_with(self.test_llm_role)
        self.assertEqual(self.improviser.llm_role_name, self.test_llm_role)
        self.assertEqual(self.improviser.llm_config, self.mock_llm_config_dict)
        print("Test Passed: NPCImproviser initialized with specific role.")

    # Patching LLMClient.call_llm_api where it's used by NPCImproviser instance
    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_successful_call_and_parsing(self, mock_call_llm_api):
        print("Running: test_improvise_npc_successful_call_and_parsing")
        name_hint = "Eleanor Vance"
        subconscious_context = "Pathos recalls a kind librarian with a penchant for mysteries."
        scene_context = {"location_description": "a dusty old library section", "pathos_mood_state": "intrigued"}

        expected_profile_dict = { # This is what the LLM is expected to return (as a JSON string)
            "id": "eleanor_vance_librarian", "name": "Eleanor Vance",
            "appearance": "Mid-50s, sharp eyes behind round spectacles, usually has a book in hand.",
            "role": "Head Archivist & Local Historian",
            "personality": "Quietly brilliant, deeply curious, and surprisingly adventurous for a librarian.",
            "relationship_to_pathos": "A new acquaintance Pathos might consult for research.",
            "initial_dialogue": "The answers you seek are often hidden in the most unexpected pages, young one."
        }
        # Configure the mock_call_llm_api to return our mock async generator yielding the JSON string
        mock_call_llm_api.return_value = mock_llm_api_response_generator(json.dumps(expected_profile_dict))

        npc_profile = await self.improviser.improvise_npc(name_hint, subconscious_context, scene_context)

        mock_call_llm_api.assert_awaited_once()
        args_passed, kwargs_passed = mock_call_llm_api.call_args
        self.assertEqual(kwargs_passed.get('llm_config'), self.mock_llm_config_dict)
        self.assertTrue(isinstance(kwargs_passed.get('messages'), list) and len(kwargs_passed.get('messages')) == 2)
        self.assertIn(name_hint, kwargs_passed['messages'][1]['content'])
        self.assertIn(subconscious_context, kwargs_passed['messages'][1]['content'])
        self.assertFalse(kwargs_passed.get('stream'))

        self.assertEqual(npc_profile, expected_profile_dict, "The returned NPC profile does not match the expected dictionary.")
        print("Test Passed: Successful async NPC improvisation and response parsing.")

    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_llm_returns_error_chunk(self, mock_call_llm_api):
        print("Running: test_improvise_npc_llm_returns_error_chunk")
        error_message = "Simulated LLM Processing Error"
        mock_call_llm_api.return_value = mock_llm_api_response_generator(error_message, is_error_chunk=True)

        with self.assertLogs(logger='eidos_agent.features.firmament.npcs.npc_improviser', level='ERROR') as log_cm:
            npc_profile = await self.improviser.improvise_npc("ErrorTestNPC", scene_context={})

        self.assertIsNone(npc_profile, "NPC profile should be None when LLMClient yields an error chunk.")
        self.assertTrue(any(f"LLMClient returned an error_chunk: {error_message}" in msg for msg in log_cm.output),
                        "Expected error message about LLMClient error_chunk not found in logs.")
        print("Test Passed: Correctly handled LLM error chunk.")

    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_llm_returns_malformed_json_string(self, mock_call_llm_api):
        print("Running: test_improvise_npc_llm_returns_malformed_json_string")
        mock_call_llm_api.return_value = mock_llm_api_response_generator(None, is_malformed_json_string=True) # Generator yields "This is { not valid json"

        with self.assertLogs(logger='eidos_agent.features.firmament.npcs.npc_improviser', level='ERROR') as log_cm:
            npc_profile = await self.improviser.improvise_npc("MalformedJSON_NPC", scene_context={})

        self.assertIsNone(npc_profile, "NPC profile should be None for malformed JSON response.")
        # Check for either "No valid JSON object found" (if regex fails) or "Failed to parse JSON" (if json.loads fails)
        self.assertTrue(any("No valid JSON object found" in msg or "Failed to parse JSON" in msg for msg in log_cm.output),
                        "Expected error message about malformed/non-existent JSON not found in logs.")
        print("Test Passed: Correctly handled malformed JSON string from LLM.")

    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_llm_returns_incomplete_json_profile(self, mock_call_llm_api):
        print("Running: test_improvise_npc_llm_returns_incomplete_json_profile")
        # The generator will yield a JSON string for an incomplete profile
        mock_call_llm_api.return_value = mock_llm_api_response_generator(None, is_incomplete_json_string=True)

        with self.assertLogs(logger='eidos_agent.features.firmament.npcs.npc_improviser', level='ERROR') as log_cm:
            npc_profile = await self.improviser.improvise_npc("IncompleteProfileNPC", scene_context={})

        self.assertIsNone(npc_profile, "NPC profile should be None if LLM returns JSON missing required fields.")
        self.assertTrue(any("LLM response missing or invalid essential key" in msg for msg in log_cm.output),
                        "Expected error about missing essential keys not found in logs.")
        print("Test Passed: Correctly handled incomplete JSON profile from LLM.")

    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_llm_returns_empty_string_content(self, mock_call_llm_api):
        print("Running: test_improvise_npc_llm_returns_empty_string_content")
        mock_call_llm_api.return_value = mock_llm_api_response_generator(None, is_empty_string=True) # Generator yields ""

        with self.assertLogs(logger='eidos_agent.features.firmament.npcs.npc_improviser', level='WARNING') as log_cm:
            npc_profile = await self.improviser.improvise_npc("EmptyContentNPC", scene_context={})

        self.assertIsNone(npc_profile, "NPC profile should be None if LLM returns an empty string.")
        self.assertTrue(any("LLM returned empty content string." in msg for msg in log_cm.output),
                        "Expected warning about empty content string not found in logs.")
        print("Test Passed: Correctly handled empty string content from LLM.")

    # Test for missing LLM config during improvise_npc call (not just init)
    async def test_improvise_npc_no_llm_url_at_call_time(self):
        print("Running: test_improvise_npc_no_llm_url_at_call_time")
        # Ensure improviser is created with a seemingly valid config initially
        improviser_temp = NPCImproviser(firmament_llm_role_name=self.test_llm_role)
        self.assertIsNotNone(improviser_temp.llm_config)

        # Now, sabotage the config's URL before calling improvise_npc
        if improviser_temp.llm_config: # Should exist based on setUp
            improviser_temp.llm_config['url'] = "" # Set URL to empty string

        with self.assertLogs(logger='eidos_agent.features.firmament.npcs.npc_improviser', level='ERROR') as log_cm:
            npc_profile = await improviser_temp.improvise_npc(scene_context={})

        self.assertIsNone(npc_profile)
        self.assertTrue(any(f"LLM URL for role '{self.test_llm_role}' is missing" in msg for msg in log_cm.output))
        print("Test Passed: Returns None if LLM URL is missing at call time.")


# This structure allows running async tests with `python -m unittest ...`
# or directly `python your_test_file.py` if unittest TestLoader handles async def methods.
# If using an older unittest version that doesn't auto-wrap, one might need:
# if __name__ == '__main__':
#     suite = unittest.TestSuite()
#     for test_name in unittest.defaultTestLoader.getTestCaseNames(TestNPCImproviser):
#         if test_name.startswith("test_"): # Assuming async tests are 'async def test_...'
#             test_method = getattr(TestNPCImproviser(methodName=test_name), test_name)
#             if asyncio.iscoroutinefunction(test_method):
#                 # A simple way to wrap, more robust solutions exist
#                 def sync_wrapper(self_test, method_to_run=test_method):
#                     return asyncio.run(method_to_run())
#                 setattr(TestNPCImproviser, test_name, sync_wrapper) # Replace async with sync wrapper
#     unittest.main(verbosity=2)

if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.DEBUG)
    unittest.main(verbosity=2)
