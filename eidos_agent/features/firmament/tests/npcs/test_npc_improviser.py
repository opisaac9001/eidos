# eidos_agent/features/firmament/tests/npcs/test_npc_improviser.py

import unittest
from unittest.mock import patch, MagicMock, AsyncMock, mock_open
import logging
import json
import asyncio
from typing import Dict, Any, AsyncGenerator, Optional, List # Added Optional, List

# Adjust import path based on actual file structure
try:
    # Try to import the actual classes first
    from eidos_agent.features.firmament.npcs.npc_improviser import NPCImproviser
    from eidos_agent.core.config import Config, LLMConfig # These are used for patching and type hints
    from eidos_agent.llm_integrations.llm_client import LLMClient # Used for patching
    from eidos_agent.core.http_client_manager import HTTPClientManager # Used for patching
except ImportError:  # pragma: no cover
    # Fallback to using dummies from npc_improviser itself if top-level import fails
    # This helps if the test is run in a context where npc_improviser.py is accessible
    # but its own internal imports of core components might fail.
    print("WARNING: NPCImproviser test using potentially dummied core components from npc_improviser.py itself.")
    try:
        from eidos_agent.features.firmament.npcs.npc_improviser import NPCImproviser, Config, LLMConfig, LLMClient, HTTPClientManager
    except ImportError:
        print("CRITICAL: NPCImproviser test imports failed completely. Using placeholder dummies.")
        LLMConfig = Dict[str, Any]  # type:ignore
        class Config:  # type:ignore
            @staticmethod
            def get_firmament_module_config(): return {"firmament_llm_role": "PH_DUMMY_FIRMAMENT_ROLE"}
            @staticmethod
            def get_llm_config(role_name_arg: str) -> Optional[LLMConfig]:
                if role_name_arg == "PH_DUMMY_FIRMAMENT_ROLE":
                    return {"role": role_name_arg, "model": "PH_generic_dummy_model", "url": "http://ph_generic_dummy_url"}
                return None
        class LLMClient:  # type:ignore
            def __init__(self, http_client: Any): pass
            async def call_llm_api(self, llm_config: LLMConfig, messages: List[Dict[str, str]], stream: bool = False, **kwargs: Any):
                yield json.dumps({"id": "placeholder_id", "name": "Placeholder NPC", "appearance": "PH", "role": "PH", "personality": "PH", "relationship_to_pathos": "PH", "initial_dialogue": "PH"})
                if False: yield # Make it a generator
        class HTTPClientManager: #type:ignore
            _instance = None
            @classmethod
            def instance(cls): cls._instance = cls._instance or cls(); return cls._instance
            def get_client(self): return MagicMock(spec=httpx.AsyncClient) # type: ignore
            async def startup(self): pass
            async def shutdown(self): pass
        class NPCImproviser:  # type:ignore
            def __init__(self, firmament_llm_role_name: Optional[str] = None):
                self.llm_role_name = firmament_llm_role_name or "PH_DUMMY_ROLE"
                self.llm_config: Optional[LLMConfig] = Config.get_llm_config(self.llm_role_name)
                self.http_client_manager = HTTPClientManager.instance()
            def _build_improvisation_prompt(self, name_hint: Any, subconscious_thought_context: Any, scene_context: Any) -> str: return "PH_dummy_prompt"
            async def improvise_npc(self, name_hint: Any = None, subconscious_thought_context: Any = None, scene_context: Any = None) -> Optional[Dict[str, Any]]:
                if not self.llm_config or not self.llm_config.get("url"): return None
                return {"id": "ph_dummy_id", "name": name_hint or "PH_DummyNPC", "appearance": "PH", "role": "PH", "personality": "PH", "relationship_to_pathos": "PH", "initial_dialogue": "PH"}
            def _normalize_id(self, text: str, suffix: str = "") -> str: # Add dummy normalize
                return text.lower().replace(" ", "_") + suffix if text else f"normalized{suffix}"

# Renamed to make_mock_llm_api_response_generator and changed to a sync function returning an async generator
def make_mock_llm_api_response_generator(
    response_data: Any = None,
    is_error_chunk: bool = False,
    is_malformed_json_string: bool = False,
    is_empty_string: bool = False,
    response_json_dict: Optional[Dict[str, Any]] = None,
    raw_string_response: Optional[str] = None
): # This is now a synchronous function
    async def _inner_async_generator() -> AsyncGenerator[Any, None]: # The actual async generator
        if is_error_chunk:
            yield {"type": "error_chunk", "payload": str(response_data) if response_data else "Simulated error"}
        elif is_malformed_json_string:
            yield "This is { not valid json because it's broken."
        elif raw_string_response is not None:
            yield raw_string_response
        elif response_json_dict is not None:
            yield json.dumps(response_json_dict)
        elif is_empty_string:
            yield ""
        elif isinstance(response_data, str): # general valid JSON string
            yield response_data
        else: # Fallback if no other condition met
            # Ensure it still yields something to be an async generator if no specific path taken
            # This case should ideally be avoided by specific test configurations.
            # For safety, yield an error or a default valid empty structure if that makes sense for non-error paths.
            # Here, erroring out if mock is misconfigured seems reasonable.
            yield {"type": "error_chunk", "payload": f"Mock LLM generator misconfigured. Data: {str(response_data)}"}

        # Ensure it's always treated as an async generator, even if no specific data yielded above (e.g. if all flags false and no dict/str)
        # This is typically not needed if one of the conditions above always yields.
        # If all paths yield, this is redundant. If a path might not yield, it ensures generator type.
        if False: # pragma: no cover
            yield None
    return _inner_async_generator() # Return the callable async generator instance


IMPROVISER_LOGGER_NAME = 'eidos_agent.features.firmament.npcs.npc_improviser'

class TestNPCImproviser(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_fm_config_patcher = patch('eidos_agent.features.firmament.npcs.npc_improviser.Config.get_firmament_module_config')
        self.mock_llm_config_patcher = patch('eidos_agent.features.firmament.npcs.npc_improviser.Config.get_llm_config')
        self.mock_http_client_manager_patcher = patch('eidos_agent.features.firmament.npcs.npc_improviser.HTTPClientManager.instance')

        self.mock_get_fm_config = self.mock_fm_config_patcher.start()
        self.mock_get_llm_config = self.mock_llm_config_patcher.start()
        self.mock_http_client_manager_instance = self.mock_http_client_manager_patcher.start()

        # Configure the HTTPClientManager mock
        self.mock_shared_async_client = AsyncMock(spec=LLMClient.__init__.__annotations__.get('http_client', MagicMock())) # httpx.AsyncClient
        mock_http_manager = MagicMock()
        mock_http_manager.get_client.return_value = self.mock_shared_async_client
        self.mock_http_client_manager_instance.return_value = mock_http_manager

        self.test_llm_role = "TEST_IMPROVISER_ROLE_VALID"
        self.test_llm_model = "test_improviser_model_v3"
        self.test_llm_url = "http://test_improviser_url_v3"
        self.mock_llm_config_dict: LLMConfig = { # type: ignore
            "role": self.test_llm_role, "model": self.test_llm_model,
            "url": self.test_llm_url, "timeout": 10.0, "temperature": 0.7, "max_tokens": 550
        }
        self.mock_get_fm_config.return_value = {"firmament_llm_role": self.test_llm_role}
        self.mock_get_llm_config.return_value = self.mock_llm_config_dict

        # Ensure logger for NPCImproviser is accessible via the class for dummy testing if needed
        # This is more for the dummy class structure if used, real class uses module logger.
        NPCImproviser.logger = logging.getLogger(IMPROVISER_LOGGER_NAME)


        self.improviser = NPCImproviser(firmament_llm_role_name=self.test_llm_role)
        # Test instance that would try to use default role from Config
        self.improviser_default_role = NPCImproviser()


    def tearDown(self):
        self.mock_fm_config_patcher.stop()
        self.mock_llm_config_patcher.stop()
        self.mock_http_client_manager_patcher.stop()
        patch.stopall() # Stop any other patches that might have been started in tests, e.g. LLMClient.call_llm_api

    def test_npc_improviser_initialization(self):
        # Test with specified role
        self.mock_get_llm_config.assert_any_call(self.test_llm_role)
        self.assertEqual(self.improviser.llm_role_name, self.test_llm_role)
        self.assertEqual(self.improviser.llm_config, self.mock_llm_config_dict)
        self.assertIsNotNone(self.improviser.http_client_manager)

        # Test with default role
        self.mock_get_fm_config.assert_called_once() # Called for improviser_default_role
        self.assertEqual(self.improviser_default_role.llm_role_name, self.test_llm_role) # As per mock_get_fm_config
        self.assertEqual(self.improviser_default_role.llm_config, self.mock_llm_config_dict)
        self.assertIsNotNone(self.improviser_default_role.http_client_manager)

    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_successful_call_and_parsing(self, mock_call_llm_api):
        name_hint = "Eleanor Vance"
        subconscious_context = "Pathos recalls a kind librarian with a penchant for mysteries."
        scene_context = {"location_description": "a dusty old library section", "pathos_mood_state": "intrigued"}

        expected_profile_dict = {
            "id": "eleanor_vance_librarian", "name": "Eleanor Vance",
            "appearance": "Mid-50s, sharp eyes behind round spectacles, usually has a book in hand.",
            "role": "Head Archivist & Local Historian",
            "personality": "Quietly brilliant, deeply curious, and surprisingly adventurous for a librarian.",
            "relationship_to_pathos": "A new acquaintance Pathos might consult for research.",
            "initial_dialogue": "The answers you seek are often hidden in the most unexpected pages, young one."
        }
        mock_call_llm_api.return_value = make_mock_llm_api_response_generator(response_json_dict=expected_profile_dict)

        npc_profile = await self.improviser.improvise_npc(name_hint, subconscious_context, scene_context)

        mock_call_llm_api.assert_called_once() # Changed from assert_awaited_once as return_value is now a direct generator
        _, kwargs_passed = mock_call_llm_api.call_args
        self.assertEqual(kwargs_passed.get('llm_config'), self.mock_llm_config_dict)

        user_prompt_content = kwargs_passed['messages'][1]['content']
        self.assertIn(name_hint, user_prompt_content)
        if subconscious_context: self.assertIn(subconscious_context, user_prompt_content)
        self.assertIn("Output ONLY a single, valid JSON object", user_prompt_content)
        self.assertIn("The 'id' MUST be a unique, lowercase, snake_case string", user_prompt_content)
        self.assertIn("lara_croft_example", user_prompt_content)

        self.assertFalse(kwargs_passed.get('stream'))
        self.assertEqual(npc_profile, expected_profile_dict)

    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_json_extraction_from_llm_text(self, mock_call_llm_api):
        expected_profile_dict = {"id": "extracted_id", "name": "Extracted NPC", "appearance": "Clear", "role": "Extractor", "personality": "Precise", "relationship_to_pathos": "Found", "initial_dialogue": "Got it!"}
        llm_response_with_markdown = f"Some introductory text from LLM.\n```json\n{json.dumps(expected_profile_dict)}\n```\nSome concluding text."
        mock_call_llm_api.return_value = make_mock_llm_api_response_generator(raw_string_response=llm_response_with_markdown)

        npc_profile = await self.improviser.improvise_npc("Extractor", scene_context={})
        self.assertEqual(npc_profile, expected_profile_dict)

    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_llm_returns_error_chunk(self, mock_call_llm_api):
        error_message = "Simulated LLM Processing Error during generation"
        mock_call_llm_api.return_value = make_mock_llm_api_response_generator(response_data=error_message, is_error_chunk=True)

        with self.assertLogs(IMPROVISER_LOGGER_NAME, level='ERROR') as log_cm:
            npc_profile = await self.improviser.improvise_npc("ErrorNPC", scene_context={})

        self.assertIsNone(npc_profile)
        self.assertTrue(any(f"LLM API error: {error_message}" in msg for msg in log_cm.output))

    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_llm_returns_malformed_json_string(self, mock_call_llm_api):
        mock_call_llm_api.return_value = make_mock_llm_api_response_generator(is_malformed_json_string=True)

        with self.assertLogs(IMPROVISER_LOGGER_NAME, level='ERROR') as log_cm:
            npc_profile = await self.improviser.improvise_npc("MalformedJSON_NPC", scene_context={})

        self.assertIsNone(npc_profile)
        self.assertTrue(any("No valid JSON object found" in msg or "JSONDecodeError" in msg for msg in log_cm.output))

    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_missing_id_generates_from_name(self, mock_call_llm_api):
        profile_missing_id = {
            "name": "Test NPC Name", "appearance": "Looks testy", "role": "Tester",
            "personality": "Thorough", "relationship_to_pathos": "Acquaintance",
            "initial_dialogue": "Testing..."
        } # id is missing
        mock_call_llm_api.return_value = make_mock_llm_api_response_generator(response_json_dict=profile_missing_id)

        with self.assertLogs(IMPROVISER_LOGGER_NAME, level='WARNING') as log_cm:
            npc_profile = await self.improviser.improvise_npc(name_hint="Test NPC Name", scene_context={})

        self.assertIsNotNone(npc_profile)
        self.assertEqual(npc_profile['id'], "test_npc_name_improv_id")
        self.assertEqual(npc_profile['name'], "Test NPC Name")
        self.assertTrue(any("Validation failed for field 'id'" in msg and "Generated new ID: 'test_npc_name_improv_id'" in msg for msg in log_cm.output))

    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_malformed_id_reformats_from_name(self, mock_call_llm_api):
        profile_malformed_id = {
            "id": "My Bad ID With Spaces", "name": "Reformat Me Kindly", "appearance": "Looks reformattable",
            "role": "Reformatter", "personality": "Flexible", "relationship_to_pathos": "Neutral",
            "initial_dialogue": "Reformatting now!"
        }
        mock_call_llm_api.return_value = make_mock_llm_api_response_generator(response_json_dict=profile_malformed_id)

        with self.assertLogs(IMPROVISER_LOGGER_NAME, level='INFO') as log_cm: # Reformatted ID is INFO level
            npc_profile = await self.improviser.improvise_npc(name_hint="Reformat Me Kindly", scene_context={})

        self.assertIsNotNone(npc_profile)
        self.assertEqual(npc_profile['id'], "reformat_me_kindly_reformatted_id")
        self.assertTrue(any("ID 'My Bad ID With Spaces' from LLM (or initial generation) is not valid lowercase snake_case." in msg for msg in log_cm.output))
        self.assertTrue(any("Reformatted ID to: 'reformat_me_kindly_reformatted_id'" in msg for msg in log_cm.output))


    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_critical_id_and_name_failure(self, mock_call_llm_api):
        profile_missing_id_and_invalid_name = {
            "name": 12345, # Invalid name type
            "appearance": "Vague", "role": "None", "personality": "Unknown",
            "relationship_to_pathos": "None", "initial_dialogue": "..."
        } # id is missing, name is not string
        mock_call_llm_api.return_value = make_mock_llm_api_response_generator(response_json_dict=profile_missing_id_and_invalid_name)

        with self.assertLogs(IMPROVISER_LOGGER_NAME, level='ERROR') as log_cm:
            npc_profile = await self.improviser.improvise_npc(scene_context={})

        self.assertIsNone(npc_profile)
        self.assertTrue(any("Validation failed for field 'id'" in msg and "Cannot generate fallback ID as 'name' field is also invalid or missing" in msg for msg in log_cm.output))

    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_missing_other_critical_field(self, mock_call_llm_api):
        profile_missing_appearance = {
            "id": "test_id_123", "name": "NoShow NPC", "role": "Actor",
            "personality": "Shy", "relationship_to_pathos": "Distant", "initial_dialogue": "Boo."
            # appearance is missing
        }
        mock_call_llm_api.return_value = make_mock_llm_api_response_generator(response_json_dict=profile_missing_appearance)

        with self.assertLogs(IMPROVISER_LOGGER_NAME, level='ERROR') as log_cm:
            npc_profile = await self.improviser.improvise_npc(name_hint="NoShow NPC", scene_context={})

        self.assertIsNone(npc_profile)
        self.assertTrue(any("Validation failed for field 'appearance'" in msg and "Field is critical and invalid. Profile discarded." in msg for msg in log_cm.output))

    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_llm_returns_empty_string_value_for_field_salvaged_by_name_hint(self, mock_call_llm_api):
        profile_empty_name_field = {
            "id": "fixed_id_123", "name": "  ", "appearance": "Okay", "role": "Tester", # name is empty string
            "personality": "Good", "relationship_to_pathos": "Okay", "initial_dialogue": "Hi"
        }
        name_hint_for_salvage = "Salvaged Valid Name"
        mock_call_llm_api.return_value = make_mock_llm_api_response_generator(response_json_dict=profile_empty_name_field)

        with self.assertLogs(IMPROVISER_LOGGER_NAME, level='WARNING') as log_cm:
            npc_profile = await self.improviser.improvise_npc(name_hint=name_hint_for_salvage, scene_context={})

        self.assertIsNotNone(npc_profile)
        self.assertEqual(npc_profile['name'], name_hint_for_salvage)
        self.assertTrue(any(f"Validation failed for field 'name'" in msg and f"Used original name_hint '{name_hint_for_salvage}' for 'name' field" in msg for msg in log_cm.output))

    @patch('eidos_agent.features.firmament.npcs.npc_improviser.LLMClient.call_llm_api', new_callable=AsyncMock)
    async def test_improvise_npc_llm_returns_empty_string_content(self, mock_call_llm_api):
        mock_call_llm_api.return_value = make_mock_llm_api_response_generator(is_empty_string=True)

        with self.assertLogs(IMPROVISER_LOGGER_NAME, level='WARNING') as log_cm:
            npc_profile = await self.improviser.improvise_npc("EmptyContentNPC", scene_context={})

        self.assertIsNone(npc_profile)
        self.assertTrue(any("LLM returned empty content." in msg for msg in log_cm.output))

    async def test_improvise_npc_no_llm_url_at_call_time(self):
        # Create a temporary improviser instance for this test
        # Ensure it gets a config, then invalidate the URL part of that config
        with patch('eidos_agent.features.firmament.npcs.npc_improviser.Config.get_llm_config') as mock_get_specific_llm_config:
            temp_llm_config_no_url = self.mock_llm_config_dict.copy()
            temp_llm_config_no_url["url"] = "" # Invalid URL
            mock_get_specific_llm_config.return_value = temp_llm_config_no_url

            improviser_no_url = NPCImproviser(firmament_llm_role_name="ROLE_WITH_NO_URL_CONFIG")
            self.assertEqual(improviser_no_url.llm_config, temp_llm_config_no_url)

            with self.assertLogs(IMPROVISER_LOGGER_NAME, level='ERROR') as log_cm:
                npc_profile = await improviser_no_url.improvise_npc(scene_context={})

            self.assertIsNone(npc_profile)
            self.assertTrue(any(f"LLM URL for role '{improviser_no_url.llm_role_name}' missing or invalid" in msg for msg in log_cm.output))

    async def test_improvise_npc_llm_config_completely_missing_at_call_time(self):
        with patch('eidos_agent.features.firmament.npcs.npc_improviser.Config.get_llm_config') as mock_get_specific_llm_config:
            mock_get_specific_llm_config.return_value = None # Simulate config not found

            improviser_no_config = NPCImproviser(firmament_llm_role_name="ROLE_WITH_NO_CONFIG_AT_ALL")
            self.assertIsNone(improviser_no_config.llm_config) # Verifies init state

            with self.assertLogs(IMPROVISER_LOGGER_NAME, level='ERROR') as log_cm:
                npc_profile = await improviser_no_config.improvise_npc(scene_context={})

            self.assertIsNone(npc_profile)
            self.assertTrue(any(f"LLM URL for role '{improviser_no_config.llm_role_name}' missing or invalid" in msg for msg in log_cm.output))

    async def test_normalize_id_functionality(self):
        # Test cases for _normalize_id (it's a protected method, but crucial for id generation)
        impr = self.improviser # Use existing instance
        self.assertEqual(impr._normalize_id("Test Name", suffix="_test_id"), "test_name_test_id")
        self.assertEqual(impr._normalize_id(" Test   Name  ", suffix="_test_id"), "test_name_test_id")
        self.assertEqual(impr._normalize_id("Test-Name!@#123", suffix="_id"), "testname123_id")
        self.assertEqual(impr._normalize_id("  !@#$  ", suffix="_id"), "sanitized_empty_name_id") # All invalid chars
        self.assertEqual(impr._normalize_id("!@#$", suffix="_id"), "sanitized_empty_name_id")
        self.assertEqual(impr._normalize_id(None, suffix="_id"), "invalid_name_for_id") # type: ignore
        self.assertEqual(impr._normalize_id("  leading_trailing_  ", suffix=""), "leading_trailing")
        self.assertEqual(impr._normalize_id("double__underscore", suffix=""), "double_underscore")
        self.assertEqual(impr._normalize_id("name", suffix=""), "name") # No suffix
        self.assertEqual(impr._normalize_id("_start", suffix="_suf"), "start_suf")
        self.assertEqual(impr._normalize_id("end_", suffix="_suf"), "end_suf")


if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.DEBUG) # Ensure logs are visible for test runs
    unittest.main(verbosity=2)
