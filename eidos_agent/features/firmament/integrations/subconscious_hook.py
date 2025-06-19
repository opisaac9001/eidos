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
    Fetches recent thoughts (memories of type 'thought' or 'received_subconscious_intention')
    from EthosCore for Pathos.
    """
    if not _ethos_core_instance:
        logger.warning("SubconsciousHook: EthosCore not initialized. Returning empty list for recent thoughts.")
        return []

    try:
        # These are typically Pathos's own thoughts or system-generated intentions for Pathos
        # PATHOS_USER_ID is imported from chronos_engine at the top of the file.
        # If that import fails, a dummy PATHOS_USER_ID is created at the module level.
        # It's assumed that the _ethos_core_instance, if real, would use the real PATHOS_USER_ID internally
        # or that its methods called with PATHOS_USER_ID would correctly resolve.
        # For this function, we use the PATHOS_USER_ID available in its scope (either real or dummy).
        user_id_for_query = PATHOS_USER_ID

        thought_memories: List[MemoryEntry] = []
        if hasattr(_ethos_core_instance, 'memory_storage') and _ethos_core_instance.memory_storage:
            # Fetch 'thought' type memories
            thoughts1 = _ethos_core_instance.memory_storage.get_entries_by_type_and_user(
                entry_type='thought',
                user_id=user_id_for_query,
                limit=limit
            )
            thought_memories.extend(thoughts1)

            intentions = _ethos_core_instance.memory_storage.get_entries_by_type_and_user(
                entry_type='received_subconscious_intention',
                user_id=user_id_for_query,
                limit=limit
            )
            thought_memories.extend(intentions)

            thought_memories.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            thought_memories = thought_memories[:limit]

        if not thought_memories:
            logger.info("SubconsciousHook: No recent thoughts/intentions found in EthosCore.")
            return []

        formatted_thoughts = []
        for mem_entry in thought_memories:
            metadata = mem_entry.get('metadata', {})
            formatted_thought = {
                "content": mem_entry.get('content', ''),
                "timestamp": mem_entry.get('timestamp', datetime.now(timezone.utc).isoformat()),
                "source": metadata.get('source_of_trigger', metadata.get('source', 'ethos_core_thought')),
                "mood_at_thought": metadata.get('mood_at_generation', metadata.get('mood', {"name": "neutral"})),
                "urgency": metadata.get('urgency_of_trigger', metadata.get('urgency', 'low')),
                "impulse_type": metadata.get('impulse_type')
            }
            formatted_thoughts.append(formatted_thought)

        logger.info(f"SubconsciousHook: Returning {len(formatted_thoughts)} formatted thoughts.")
        return formatted_thoughts

    except Exception as e:
        logger.error(f"SubconsciousHook: Error fetching thoughts from EthosCore: {e}", exc_info=True)
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

        # Setup Mock EthosCore and MemoryStorage
        class MockMemoryStorage:
            def get_entries_by_type_and_user(self, entry_type: str, user_id: str, limit: int) -> List[Dict[str, Any]]:
                logger.info(f"MockMemoryStorage.get_entries_by_type_and_user called for type '{entry_type}', user '{user_id}' (Expected: {TEST_PATHOS_USER_ID}), limit {limit}")
                assert user_id == TEST_PATHOS_USER_ID, f"MockMemoryStorage expected user_id {TEST_PATHOS_USER_ID}, got {user_id}"
                if entry_type == 'thought':
                    return [{"content": "Mocked thought 1 from Ethos.", "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(), "metadata": {"source": "mock_ethos", "mood_at_generation": {"name": "curious"}, "urgency": "low"}, 'type': 'thought', 'id': 't1'}]
                if entry_type == 'received_subconscious_intention':
                    return [{"content": "Mocked intention: Investigate AI ethics.", "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(), "metadata": {"source": "mock_subconscious_node", "urgency": "medium", "impulse_type": "research_ai_ethics"}, 'type': 'received_subconscious_intention', 'id': 'i1'}]
                return []

        class MockEthosCoreForSubconscious:
            PATHOS_USER_ID = TEST_PATHOS_USER_ID
            def __init__(self):
                self.memory_storage = MockMemoryStorage()
                logger.info("MockEthosCoreForSubconscious initialized with MockMemoryStorage.")

        mock_ethos_sub_hook = MockEthosCoreForSubconscious()
        set_ethos_core_for_subconscious_hook(mock_ethos_sub_hook) # type: ignore

        # Test get_recent_subconscious_thoughts
        print("\n--- Testing get_recent_subconscious_thoughts (with mock EthosCore) ---")
        recent_thoughts = get_recent_subconscious_thoughts(limit=3)
        print(f"Retrieved thoughts: {json.dumps(recent_thoughts, indent=2)}")
        assert len(recent_thoughts) <= 3
        assert len(recent_thoughts) > 0, "Expected mock EthosCore to return some thoughts"
        # Check if combined and sorted correctly (intention should be older than thought in mock)
        if len(recent_thoughts) == 2: # Assuming limit >= 2
            assert recent_thoughts[0]['content'] == "Mocked thought 1 from Ethos." # Newer
            assert recent_thoughts[1]['content'] == "Mocked intention: Investigate AI ethics." # Older

        # Setup a mock EventBus to capture outputs of handle_thought_trigger
        _test_events_sh_main_guidance = []
        class MockEventBusSHGuidance(EventBus): # type: ignore
            def publish(self, event_type: str, data: dict):
                print(f"    [SubconsciousHook MainTest Capture] Event: {event_type}, Data: {str(data)[:120]}...")
                _test_events_sh_main_guidance.append({"event_type": event_type, "data": data})

        original_event_bus_sh_guidance = EventBus.instance # type: ignore
        EventBus.instance = lambda: MockEventBusSHGuidance() # type: ignore

        # Test handle_thought_trigger (which might use LLM or dummy)
        print("\n--- Testing handle_thought_trigger ---")
        # Use one of the thoughts fetched (or a new one) for handle_thought_trigger
        trigger_payload_for_handler = {
            "content": "A new thought just occurred: what if the sky is green elsewhere?",
            "mood": {"name": "pensive"}, "urgency": "low", "source":"test_main_direct_trigger",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        print(f"Triggering handle_thought_trigger with: {trigger_payload_for_handler.get('content')}")
        await handle_thought_trigger(trigger_payload_for_handler)
        await asyncio.sleep(0.1)

        print("\n--- Subconscious Hook Test Run Completed ---")
        print("Review logs above for 'LLM elaborated thought to...' messages or errors.")
        print(f"Total events captured by mock EventBus for handle_thought_trigger: {len(_test_events_sh_main_guidance)}")
        for evt in _test_events_sh_main_guidance:
             if evt["event_type"] == "memory.write" and evt["data"].get("type") == "thought": # type: ignore
                 print(f"  Logged thought content from handle_thought_trigger: {evt['data'].get('content')}") # type: ignore

        EventBus.instance = original_event_bus_sh_guidance # Restore

        # Attempt to shutdown HTTPClientManager if it was used
        if 'HTTPClientManager' in globals() and callable(globals()['HTTPClientManager'].instance): # type: ignore
            mgr_instance = HTTPClientManager.instance() # type: ignore
            is_real_http_manager = not ("dummy" in str(type(mgr_instance)).lower())
            if is_real_http_manager and hasattr(mgr_instance, 'shutdown') and asyncio.iscoroutinefunction(mgr_instance.shutdown):
                print("Attempting HTTPClientManager shutdown...")
                await mgr_instance.shutdown()


    asyncio.run(main_test_subconscious_hook_llm_guidance())
    print("\nConsider running `python -m eidos_agent.features.firmament.integrations.subconscious_hook` directly for testing.")
