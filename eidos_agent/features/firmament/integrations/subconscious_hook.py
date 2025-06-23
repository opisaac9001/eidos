# eidos_agent/features/firmament/integrations/subconscious_hook.py
import logging
import httpx # Though not used directly in this file after refactor, LLMClient needs it.
import json
import re
import asyncio # For async def

from typing import List, Dict, Any, Optional

from ..core.event_bus import EventBus
from ..core.event_types import THOUGHT_TRIGGER, IMPULSE
from datetime import datetime, timezone, timedelta

try:
    from ....core.config import Config, LLMConfig
    from ....llm_integrations.llm_client import LLMClient
    from ....core.http_client_manager import HTTPClientManager # New import
    from ....persona_logic.ethos_core.core import EthosCore
    from ....persona_logic.ethos_core.memory_storage import MemoryEntry
    from .....persona_logic.chronos_engine import PATHOS_USER_ID # For use in get_recent_subconscious_thoughts
except ImportError as e: # pragma: no cover
    print(f"CRITICAL IMPORT ERROR in subconscious_hook.py: {e}. Using dummies.")
    class Config: #type:ignore
        @staticmethod
        def get_firmament_module_config(): return {"firmament_llm_role": "DUMMY_FIRMAMENT_ROLE"}
        @staticmethod
        def get_llm_config(role_name_arg):
            return {"url": "dummy_url", "model": "d_model_sh_dummy", "timeout":10.0, "temperature":0.7, "max_tokens":128} if role_name_arg=="DUMMY_FIRMAMENT_ROLE" else None
    LLMConfig = Dict[str, Any]; #type:ignore
    MemoryEntry = Dict[str, Any] #type: ignore

    class LLMClient: #type:ignore
        """Dummy LLMClient for use when actual import fails."""
        def __init__(self, http_client: Any):
            self.http_client = http_client # http_client will be a MagicMock from dummy HTTPClientManager
            # print(f"Dummy LLMClient (subconscious_hook) initialized with http_client: {self.http_client}")

        async def call_llm_api(self, llm_config: LLMConfig, messages: List[Dict[str, str]], stream: bool = False, **kwargs):
            # print(f"DUMMY LLMClient (subconscious_hook).call_llm_api called. Role: {llm_config.get('role')}")
            last_user_message_content = "no user message found"
            if messages and isinstance(messages, list):
                user_messages = [m.get("content") for m in messages if m.get("role") == "user"]
                if user_messages: last_user_message_content = user_messages[-1]

            # Simulate a slightly more useful elaboration based on the input prompt
            elaboration_base = last_user_message_content.replace("Internal monologue: ", "")
            yield f"This is a dummy LLM elaboration of the thought: '{elaboration_base}'. It seems quite profound when you think about it from a simulated perspective."
            if False: yield # Makes it an async generator

    from unittest.mock import MagicMock # For dummy HTTPClientManager
    class HTTPClientManager: #type:ignore
        _instance = None
        @classmethod
        def instance(cls):
            if not cls._instance:
                # print("Dummy HTTPClientManager (subconscious_hook): Creating new instance.")
                cls._instance = cls()
            return cls._instance
        def get_client(self):
            # print("Dummy HTTPClientManager (subconscious_hook): get_client() called, returning MagicMock.")
            mock_client = MagicMock(spec=httpx.AsyncClient if 'httpx' in globals() else object)
            mock_client.is_closed = False
            return mock_client
        async def shutdown(self): pass

    class EthosCore: # type: ignore
        PATHOS_USER_ID = "pathos_dummy_ethos_user" # Dummy for EthosCore
        def __init__(self, config: Any):
            print("DummyEthosCore (subconscious_hook) initialized.")
            self.memory_storage = None # Or a dummy MemoryStorage if methods are called on it

        async def get_entries_by_type_and_user(self, entry_type: str, user_id: str, limit: int) -> List[MemoryEntry]:
            logger.warning("DummyEthosCore.get_entries_by_type_and_user called. Returning empty list.")
            return []

    PATHOS_USER_ID = "pathos_dummy_user_id_if_chronos_import_fails" # Dummy for PATHOS_USER_ID from chronos_engine

logger = logging.getLogger(__name__)
_ethos_core_instance: Optional[EthosCore] = None

def set_ethos_core_for_subconscious_hook(ethos_core: EthosCore):
    global _ethos_core_instance
    _ethos_core_instance = ethos_core
    logger.info(f"SubconsciousHook: EthosCore instance set. {_ethos_core_instance is not None}")

def get_recent_subconscious_thoughts(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Fetches recent thoughts and imprints from EthosCore for Pathos.
    Returns a list of dictionaries, each representing a memory entry,
    with an added 'primary_display_content' field.
    """
    if not _ethos_core_instance:
        logger.warning("SubconsciousHook: EthosCore not initialized. Returning empty list for recent thoughts/imprints.")
        return []

    try:
        pathos_user_id = PATHOS_USER_ID # Available from module-level import or dummy

        imprint_memories: List[MemoryEntry] = []
        thought_memories: List[MemoryEntry] = []

        if hasattr(_ethos_core_instance, 'memory_storage') and _ethos_core_instance.memory_storage:
            # These are synchronous calls as per MemoryStorage's current design
            imprint_memories = _ethos_core_instance.memory_storage.get_entries_by_type_and_user(
                entry_type='subconscious_imprint', user_id=pathos_user_id, limit=limit * 2
            )
            thought_memories = _ethos_core_instance.memory_storage.get_entries_by_type_and_user(
                entry_type='thought', user_id=pathos_user_id, limit=limit * 2
            )
        else:
            logger.warning("SubconsciousHook: EthosCore.memory_storage not available. Cannot fetch thoughts/imprints.")
            return []

        combined_memories = imprint_memories + thought_memories
        # Sort by timestamp in descending order (most recent first)
        combined_memories.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        # Limit to the requested number of entries
        final_memories_to_process = combined_memories[:limit]

        if not final_memories_to_process:
            logger.info("SubconsciousHook: No recent 'subconscious_imprint' or 'thought' memories found to process.")
            return []

        processed_entries: List[Dict[str, Any]] = []
        for mem_entry in final_memories_to_process:
            entry_type = mem_entry.get('type')
            entry_id = mem_entry.get('id', 'unknown_id')

            processed_entry_dict: Dict[str, Any] = {
                "id": entry_id,
                "timestamp": mem_entry.get('timestamp'),
                "type": entry_type,
                "content": mem_entry.get('content'), # Original content (elaborated for thoughts)
                "metadata": mem_entry.get('metadata', {}).copy(), # Ensure a copy
                "salience": mem_entry.get('salience'),
                "primary_display_content": "" # Initialize
            }

            if entry_type == 'thought':
                elaborated_content = mem_entry.get('content')
                if elaborated_content and str(elaborated_content).strip():
                    processed_entry_dict["primary_display_content"] = str(elaborated_content).strip()
                    logger.debug(f"Using elaborated content for thought ID {entry_id} as primary_display_content.")
                else:
                    raw_content = mem_entry.get('metadata', {}).get('raw_trigger_content')
                    if raw_content and str(raw_content).strip():
                        processed_entry_dict["primary_display_content"] = str(raw_content).strip()
                        logger.debug(f"Using raw_trigger_content for thought ID {entry_id} as primary_display_content.")
                    else:
                        processed_entry_dict["primary_display_content"] = "[empty thought content]"
                        logger.warning(f"Thought ID {entry_id} has no usable content for primary_display_content.")

            elif entry_type == 'subconscious_imprint':
                imprint_content = mem_entry.get('content')
                if imprint_content and str(imprint_content).strip():
                    processed_entry_dict["primary_display_content"] = str(imprint_content).strip()
                    logger.debug(f"Using content for subconscious_imprint ID {entry_id} as primary_display_content.")
                else:
                    processed_entry_dict["primary_display_content"] = "[empty imprint content]"
                    logger.warning(f"Subconscious_imprint ID {entry_id} has no usable content for primary_display_content.")

            else: # Should not happen
                logger.warning(f"Unexpected memory type '{entry_type}' ID {entry_id}. Setting placeholder display content.")
                processed_entry_dict["primary_display_content"] = "[unknown memory type content]"

            processed_entries.append(processed_entry_dict)

        logger.info(f"SubconsciousHook: Returning {len(processed_entries)} processed thoughts/imprints (dictionaries) (limit: {limit}).")
        return processed_entries

    except Exception as e:
        logger.error(f"SubconsciousHook: Error fetching or processing recent thoughts/imprints: {e}", exc_info=True)
        return []

async def handle_thought_trigger(payload: dict): # Changed to async def
    """
    Handles a THOUGHT_TRIGGER payload. Fetches Firmament's LLM config,
    constructs a prompt, calls an LLM (via LLMClient and shared HTTPClientManager)
    to elaborate the thought, publishes the elaborated thought to memory, and
    if deemed actionable, also publishes an IMPULSE event.
    """
    # logger.debug(f"SubconsciousHook: Async handle_thought_trigger received payload: {payload}")
    if not isinstance(payload, dict):
        logger.error("Payload for thought trigger must be a dictionary."); return

    raw_content = payload.get("content")
    mood_context = payload.get("mood", payload.get("mood_at_thought", "neutral"))
    if isinstance(mood_context, dict): mood_context = mood_context.get("name", "neutral")

    trigger_source = payload.get("source", "unknown_trigger_source")
    urgency = payload.get("urgency", "low")

    if not raw_content:
        logger.error("'content' (raw thought) is missing from thought trigger payload."); return

    logger.info(f"SubconsciousHook: Processing raw thought for elaboration: \"{raw_content}\"")
    elaborated_thought_content = raw_content # Default fallback if LLM call fails or is skipped

    firmament_module_cfg = Config.get_firmament_module_config() if callable(getattr(Config, 'get_firmament_module_config', None)) else {}
    llm_role = firmament_module_cfg.get("firmament_llm_role", "FIRMAMENT_PRIMARY")
    firmament_llm_config: Optional[LLMConfig] = Config.get_llm_config(llm_role) if callable(getattr(Config, 'get_llm_config', None)) else None

    if firmament_llm_config and firmament_llm_config.get("url") and "dummy_url" not in firmament_llm_config.get("url",""): # Check for valid URL
        http_client_mgr = HTTPClientManager.instance() # Get shared manager
        shared_httpx_client = http_client_mgr.get_client() # Get shared client

        if shared_httpx_client:
            llm_api_client = LLMClient(http_client=shared_httpx_client)

            # --- Refined System Prompt ---
            system_prompt_elaborate = (
                "You are Pathos's inner voice, responsible for elaborating on brief thoughts or observations. "
                "Take the provided 'Internal monologue' and expand it slightly into a natural-sounding, reflective thought, "
                "maintaining the original mood and intent. The elaboration should be concise, typically 1-2 sentences. "
                "Do not be conversational with an external user; directly provide the elaborated thought as if it's Pathos's own "
                "internal continuation. Do not add preambles like 'Okay, here's the elaboration:' or any quotation marks "
                "around the final thought itself unless it's direct speech within the thought."
            )
            user_prompt_elaborate = f"Internal monologue: {raw_content}\nPathos's current mood context for this thought: {mood_context}"
            messages = [
                {"role": "system", "content": system_prompt_elaborate},
                {"role": "user", "content": user_prompt_elaborate}
            ]
            logger.info(f"SubconsciousHook: Calling LLM (Role: {llm_role}, Model: {firmament_llm_config.get('model', 'N/A')}) for thought elaboration.")
            # logger.debug(f"SubconsciousHook LLM User Prompt: {user_prompt_elaborate}") # Can be verbose

            full_response_str = ""
            llm_error_detail = None
            try:
                response_gen = llm_api_client.call_llm_api(
                    llm_config=firmament_llm_config, messages=messages, stream=False
                )
                async for chunk in response_gen:
                    if isinstance(chunk, str): full_response_str += chunk
                    elif isinstance(chunk, dict) and chunk.get("type") == "error_chunk":
                        llm_error_detail = chunk.get("payload"); break

                if llm_error_detail:
                    logger.error(f"LLM API error during thought elaboration for '{raw_content[:50]}...': {llm_error_detail}. Using raw_content.")
                elif not full_response_str.strip():
                    logger.warning(f"LLM returned empty elaboration for '{raw_content[:50]}...'. Using raw_content.")
                else:
                    # Basic cleanup: strip whitespace.
                    elaborated_thought_content = full_response_str.strip()
                    # Remove potential surrounding quotes if LLM still adds them
                    if elaborated_thought_content.startswith('"') and elaborated_thought_content.endswith('"'):
                        elaborated_thought_content = elaborated_thought_content[1:-1]
                    if elaborated_thought_content.startswith("'") and elaborated_thought_content.endswith("'"):
                        elaborated_thought_content = elaborated_thought_content[1:-1]
                    logger.info(f"SubconsciousHook: LLM elaborated thought for '{raw_content[:50]}...' to '{elaborated_thought_content[:100]}...'")
            except Exception as e: # pragma: no cover
                logger.error(f"Error calling LLM for thought elaboration or processing response: {e}", exc_info=True)
                # Fallback to raw_content is already set, log this explicitly
                logger.info(f"SubconsciousHook: Using raw_content for '{raw_content[:50]}...' due to exception during LLM call/processing.")
        else: # pragma: no cover
            logger.error("SubconsciousHook: Failed to get shared HTTP client for thought elaboration. Using raw content.")
    else:
        logger.warning(f"SubconsciousHook: LLM config for role '{llm_role}' not found or URL missing. Using raw content for elaboration for '{raw_content[:50]}...'.")

    # --- Event Publishing Logic ---
    current_time_iso = payload.get("timestamp", datetime.now(timezone.utc).isoformat())
    memory_entry = {
        "type": "thought", "content": elaborated_thought_content, "raw_trigger_content": raw_content,
        "mood_at_generation": mood_context, "source_of_trigger": trigger_source,
        "urgency_of_trigger": urgency, "timestamp": current_time_iso
    }
    EventBus.instance().publish("memory.write", memory_entry)

    actionable_keywords = ["i should", "i need to", "maybe i can", "let's try to", "what if i", "i must", "i want to", "i have to", "better check", "time to", "remember to"]
    if any(keyword in raw_content.lower() for keyword in actionable_keywords) or \
       (isinstance(urgency, str) and urgency.lower() in ["medium", "high", "critical"]):
        impulse_data = {
            "type": payload.get("impulse_type", "generic_actionable_thought"),
            "original_thought_content": raw_content, "elaborated_thought_content": elaborated_thought_content,
            "mood": mood_context, "urgency": urgency, "source": trigger_source, "timestamp": current_time_iso
        }
        EventBus.instance().publish(IMPULSE, impulse_data)

def register_thought_trigger_handler():
    EventBus.instance().subscribe(THOUGHT_TRIGGER, handle_thought_trigger)
    # logger.info("SubconsciousHook: Registered ASYNC handle_thought_trigger for THOUGHT_TRIGGER events.")


if __name__ == '__main__': # pragma: no cover
    import unittest.mock # Added for mocking
    from ....services.memory_event_listener import handle_memory_write_event as memory_listener_handler, set_ethos_core_for_memory_event_listener

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # Set specific loggers to DEBUG if more detail is needed
    logging.getLogger('eidos_agent.features.firmament.integrations.subconscious_hook').setLevel(logging.DEBUG)
    # logging.getLogger('eidos_agent.llm_integrations.llm_client').setLevel(logging.DEBUG)

    # For test, import the PATHOS_USER_ID that the real code would try to import
    # This ensures the mock uses the same ID for assertions if needed.
    try:
        from .....persona_logic.chronos_engine import PATHOS_USER_ID as TEST_PATHOS_USER_ID
    except ImportError:
        TEST_PATHOS_USER_ID = "pathos_dummy_user_id_for_test" # Fallback for test if main import fails
        print(f"SubconsciousHook Test: Failed to import real PATHOS_USER_ID, using test fallback: {TEST_PATHOS_USER_ID}")


    async def test_get_recent_thoughts_logic(mock_ethos_core_for_test: MockEthosCoreForSubconscious):
        logger.info("\n\n--- Starting: test_get_recent_thoughts_logic ---")

        # Test Case 1: Empty Result
        logger.info("Test Case 1: Empty Result")
        mock_ethos_core_for_test.memory_storage.set_mock_data({})
        result_dicts = get_recent_subconscious_thoughts(limit=5)
        assert len(result_dicts) == 0, f"Expected 0 results, got {len(result_dicts)}"
        logger.info("Test Case 1 Passed.")

        # Test Case 2: Thoughts Only (Elaborated vs. Raw)
        logger.info("\nTest Case 2: Thoughts Only (Elaborated vs. Raw)")
        thought1_elaborated = {"id": "t1", "type": "thought", "content": "Elaborated T1", "metadata": {"raw_trigger_content": "Raw T1"}, "timestamp": "2023-01-01T10:00:00Z"}
        thought2_raw_only = {"id": "t2", "type": "thought", "content": "", "metadata": {"raw_trigger_content": "Raw T2 only"}, "timestamp": "2023-01-01T09:00:00Z"}
        mock_ethos_core_for_test.memory_storage.set_mock_data({"thought": [thought1_elaborated, thought2_raw_only]})
        result_dicts = get_recent_subconscious_thoughts(limit=2)
        assert len(result_dicts) == 2, f"Expected 2 results, got {len(result_dicts)}"
        assert result_dicts[0]['primary_display_content'] == "Elaborated T1", f"Got: {result_dicts[0]['primary_display_content']}"
        assert result_dicts[1]['primary_display_content'] == "Raw T2 only", f"Got: {result_dicts[1]['primary_display_content']}"
        logger.info("Test Case 2 Passed.")

        # Test Case 3: Imprints Only
        logger.info("\nTest Case 3: Imprints Only")
        imprint1 = {"id": "i1", "type": "subconscious_imprint", "content": "Imprint Content 1", "timestamp": "2023-01-01T12:00:00Z", "metadata": {}}
        imprint2 = {"id": "i2", "type": "subconscious_imprint", "content": "Imprint Content 2", "timestamp": "2023-01-01T11:00:00Z", "metadata": {}}
        mock_ethos_core_for_test.memory_storage.set_mock_data({"subconscious_imprint": [imprint1, imprint2]})
        result_dicts = get_recent_subconscious_thoughts(limit=2)
        assert len(result_dicts) == 2, f"Expected 2 results, got {len(result_dicts)}"
        assert result_dicts[0]['primary_display_content'] == "Imprint Content 1", f"Got: {result_dicts[0]['primary_display_content']}"
        logger.info("Test Case 3 Passed.")

        # Test Case 4: Mixed, Order, Limit
        logger.info("\nTest Case 4: Mixed, Order, Limit")
        thought_new = {"id": "t_new", "type": "thought", "content": "Newest thought", "metadata": {}, "timestamp": "2023-01-01T14:00:00Z"}
        imprint_mid = {"id": "i_mid", "type": "subconscious_imprint", "content": "Middle imprint", "timestamp": "2023-01-01T13:00:00Z", "metadata": {}}
        thought_old = {"id": "t_old", "type": "thought", "content": "Older thought", "metadata": {}, "timestamp": "2023-01-01T12:30:00Z"}
        mock_ethos_core_for_test.memory_storage.set_mock_data({"thought": [thought_new, thought_old], "subconscious_imprint": [imprint_mid]})
        result_dicts = get_recent_subconscious_thoughts(limit=2)
        assert len(result_dicts) == 2, f"Expected 2 results, got {len(result_dicts)}"
        assert result_dicts[0]['primary_display_content'] == "Newest thought", f"Got: {result_dicts[0]['primary_display_content']}"
        assert result_dicts[1]['primary_display_content'] == "Middle imprint", f"Got: {result_dicts[1]['primary_display_content']}"
        logger.info("Test Case 4 Passed.")

        # Test Case 5: Content Missing (Thoughts)
        logger.info("\nTest Case 5: Content Missing (Thoughts)")
        thought_both_empty = {"id": "t_empty", "type": "thought", "content": None, "metadata": {"raw_trigger_content": ""}, "timestamp": "2023-01-01T15:00:00Z"}
        mock_ethos_core_for_test.memory_storage.set_mock_data({"thought": [thought_both_empty]})
        result_dicts = get_recent_subconscious_thoughts(limit=1)
        assert len(result_dicts) == 1, f"Expected 1 result, got {len(result_dicts)}"
        assert result_dicts[0]['primary_display_content'] == "[empty thought content]", f"Got: {result_dicts[0]['primary_display_content']}"
        logger.info("Test Case 5 Passed.")

        # Test Case 6: Content Missing (Imprints)
        logger.info("\nTest Case 6: Content Missing (Imprints)")
        imprint_empty = {"id": "i_empty", "type": "subconscious_imprint", "content": " ", "timestamp": "2023-01-01T16:00:00Z", "metadata": {}}
        mock_ethos_core_for_test.memory_storage.set_mock_data({"subconscious_imprint": [imprint_empty]})
        result_dicts = get_recent_subconscious_thoughts(limit=1)
        assert len(result_dicts) == 1, f"Expected 1 result, got {len(result_dicts)}"
        assert result_dicts[0]['primary_display_content'] == "[empty imprint content]", f"Got: {result_dicts[0]['primary_display_content']}"
        logger.info("Test Case 6 Passed.")

        logger.info("--- Finished: test_get_recent_thoughts_logic ---")

    async def main_test_subconscious_hook_llm_guidance():
        print("\n" + "="*80)
        print("Subconscious Hook Standalone Test Script (Thought Elaboration & Memory Fetch)")
        print("="*80)
        print("This script will test thought elaboration (potentially using Firmament LLM) and")
        print("the fetching of recent subconscious thoughts using a mocked EthosCore.")
        print("Please ensure your .env file has Firmament LLM variables correctly set if you expect real LLM calls:")
        print("  - LLM_FIRMAMENT_PRIMARY_URL:     (e.g., http://localhost:11434/v1 for Ollama)")
        print("  - LLM_FIRMAMENT_PRIMARY_MODEL:   (e.g., llama3:8b-instruct, mistral, phi3)")
        print("  - LLM_FIRMAMENT_PRIMARY_API_KEY: (e.g., 'ollama', 'lm-studio', or your actual key if required)")
        print("If these are not set, or if core Eidos components cannot be imported, this script")
        print("will fall back to using a DUMMY LLMClient or simplified elaboration.")
        print("Set logging level to DEBUG for this script's logger to see more details.")
        print("="*80 + "\n")

        # Check current LLM config that handle_thought_trigger would use
        current_fm_cfg = Config.get_firmament_module_config() if callable(getattr(Config, 'get_firmament_module_config', None)) else {}
        current_llm_role = current_fm_cfg.get("firmament_llm_role", "FIRMAMENT_PRIMARY")
        current_llm_cfg = Config.get_llm_config(current_llm_role) if callable(getattr(Config, 'get_llm_config', None)) else {}

        is_dummy_llm_client = "dummy" in LLMClient.__name__.lower() or "dummy" in str(type(LLMClient)).lower()

        if not current_llm_cfg or not current_llm_cfg.get("url") or \
           "dummy" in current_llm_cfg.get("url", "").lower() or \
           is_dummy_llm_client:
            logger.warning("Running subconscious_hook test with DUMMY LLM configuration or DUMMY LLMClient. "
                           "Thought elaboration will be a placeholder or use raw content.\n")
        else:
            logger.info(f"Attempting REAL LLM calls for thought elaboration using role: '{current_llm_role}', "
                        f"model: '{current_llm_cfg.get('model')}', URL: '{current_llm_cfg.get('url')}'.\n")

        # Setup Mock EthosCore and MemoryStorage (Step 1: Refactor Mocks)
        class MockMemoryStorage:
            def __init__(self):
                self.mock_data: Dict[str, List[Dict[str, Any]]] = {}
                logger.info("MockMemoryStorage initialized.")

            def set_mock_data(self, data_map: Dict[str, List[Dict[str, Any]]]):
                self.mock_data = data_map
                logger.info(f"MockMemoryStorage mock_data set: {list(self.mock_data.keys())}")

            def get_entries_by_type_and_user(self, entry_type: str, user_id: str, limit: int) -> List[Dict[str, Any]]:
                logger.info(f"MockMemoryStorage.get_entries_by_type_and_user called for type '{entry_type}', user '{user_id}' (Expected: {TEST_PATHOS_USER_ID}), limit {limit}")
                if user_id != TEST_PATHOS_USER_ID:
                    logger.error(f"MockMemoryStorage expected user_id {TEST_PATHOS_USER_ID}, got {user_id}")
                    return []
                # Return a copy to allow for modification by the caller if needed, without affecting the mock's source data.
                # The limit application here is simplified; the function under test (get_recent_subconscious_thoughts)
                # fetches more initially (limit * 2 for each type) then combines, sorts, and limits.
                # This mock just needs to provide enough data for those operations to be tested.
                return self.mock_data.get(entry_type, [])[:]

        class MockEthosCoreForSubconscious:
            PATHOS_USER_ID = TEST_PATHOS_USER_ID
            def __init__(self):
                self.memory_storage = MockMemoryStorage()
                self.async_add_memory_entry_mock = unittest.mock.AsyncMock(return_value={"id": "mock_added_entry_id"})
                logger.info("MockEthosCoreForSubconscious initialized with new MockMemoryStorage and async_add_memory_entry_mock.")

            async def add_memory_entry(self, entry_data, user_id_context=None):
                logger.info(f"MockEthosCoreForSubconscious.add_memory_entry called with type: {entry_data.get('type')}, user_context: {user_id_context}")
                return await self.async_add_memory_entry_mock(entry_data, user_id_context)

        mock_ethos_sub_hook = MockEthosCoreForSubconscious() # Instantiated with new MockMemoryStorage
        set_ethos_core_for_subconscious_hook(mock_ethos_sub_hook) # type: ignore

        # Call the new detailed tests for get_recent_subconscious_thoughts
        await test_get_recent_thoughts_logic(mock_ethos_sub_hook)

        # Setup for handle_thought_trigger test
        _test_events_sh_main_guidance = []
        class MockEventBusSHGuidance(EventBus): # type: ignore
            def publish(self, event_type: str, data: dict):
                print(f"    [SubconsciousHook MainTest Capture] Event: {event_type}, Data: {str(data)[:120]}...")
                _test_events_sh_main_guidance.append({"event_type": event_type, "data": data})

        original_event_bus_sh_guidance = EventBus.instance # type: ignore
        EventBus.instance = lambda: MockEventBusSHGuidance() # type: ignore

        # Set the mocked EthosCore instance for the memory event listener
        set_ethos_core_for_memory_event_listener(mock_ethos_sub_hook)

        # Get the test event bus instance
        mock_bus_instance_sh_guidance = EventBus.instance()
        if hasattr(mock_bus_instance_sh_guidance, 'subscribe'):
            mock_bus_instance_sh_guidance.subscribe("memory.write", memory_listener_handler) # type: ignore
            logger.info("SubconsciousHook MainTest: Subscribed real memory_listener_handler to mock event bus for 'memory.write'.")
        else:
            logger.error("SubconsciousHook MainTest: Could not find mock_bus_instance_sh_guidance to subscribe memory_listener_handler.")


        # Test handle_thought_trigger (which might use LLM or dummy)
        print("\n--- Testing handle_thought_trigger ---")
        trigger_payload_for_handler = {
            "content": "A new thought just occurred: what if the sky is green elsewhere?",
            "mood": {"name": "pensive"}, "urgency": "low", "source":"test_main_direct_trigger",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        logger.info(f"Publishing THOUGHT_TRIGGER event with: {trigger_payload_for_handler.get('content')}")
        # from ..core.event_types import THOUGHT_TRIGGER # Already imported in main file
        if hasattr(mock_bus_instance_sh_guidance, 'publish'):
            mock_bus_instance_sh_guidance.publish(THOUGHT_TRIGGER, trigger_payload_for_handler) # type: ignore
            await asyncio.sleep(0.2) # Allow time for async handlers to process
        else:
            logger.error("SubconsciousHook MainTest: mock_bus_instance_sh_guidance not found to publish THOUGHT_TRIGGER.")


        print("\n--- Subconscious Hook Test Run Completed ---")
        print("Review logs above for 'LLM elaborated thought to...' messages or errors.")
        print(f"Total events captured by mock EventBus for handle_thought_trigger: {len(_test_events_sh_main_guidance)}")

        # Verify EthosCore.add_memory_entry mock calls from memory_listener_handler
        logger.info("Verifying EthosCore.add_memory_entry mock calls...")
        # handle_thought_trigger publishes to "memory.write", which memory_listener_handler listens to,
        # then memory_listener_handler calls ethos_core.add_memory_entry.
        mock_ethos_sub_hook.async_add_memory_entry_mock.assert_called_once()

        # Check the arguments of the call to the mock
        # The mock was called with (entry_data, user_id_context)
        # We want the first argument (entry_data), which is at index 0 of args list (call_args[0])
        # and it's the first element of that inner list/tuple (call_args[0][0])
        if mock_ethos_sub_hook.async_add_memory_entry_mock.call_args:
            call_args = mock_ethos_sub_hook.async_add_memory_entry_mock.call_args[0][0]
            assert call_args.get('type') == "thought", f"Expected memory type 'thought', got {call_args.get('type')}"
            assert call_args.get('raw_trigger_content') == trigger_payload_for_handler['content'], "Raw content mismatch"
            assert "dummy LLM elaboration of the thought: '" + trigger_payload_for_handler['content'] + "'" in call_args.get('content'), "Elaborated content mismatch"
            assert call_args.get('mood_at_generation') == trigger_payload_for_handler['mood']['name'], "Mood mismatch"
            assert call_args.get('source_of_trigger') == trigger_payload_for_handler['source'], "Source mismatch"
            logger.info("Assertions for EthosCore.add_memory_entry (mocked) passed successfully for 'thought' creation.")
        else:
            assert False, "async_add_memory_entry_mock was called but call_args is None (should not happen if assert_called_once passed)"

        EventBus.instance = original_event_bus_sh_guidance # Restore

        # Attempt to shutdown HTTPClientManager if it was used
        set_ethos_core_for_memory_event_listener(None) # Cleanup listener's EthosCore
        if 'HTTPClientManager' in globals() and callable(globals()['HTTPClientManager'].instance): # type: ignore
            mgr_instance = HTTPClientManager.instance() # type: ignore
            is_real_http_manager = not ("dummy" in str(type(mgr_instance)).lower())
            if is_real_http_manager and hasattr(mgr_instance, 'shutdown') and asyncio.iscoroutinefunction(mgr_instance.shutdown):
                print("Attempting HTTPClientManager shutdown...")
                await mgr_instance.shutdown()


    asyncio.run(main_test_subconscious_hook_llm_guidance())
    print("\nConsider running `python -m eidos_agent.features.firmament.integrations.subconscious_hook` directly for testing.")
