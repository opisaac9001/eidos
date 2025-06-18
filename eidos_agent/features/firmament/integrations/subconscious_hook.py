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
except ImportError as e: # pragma: no cover
    print(f"CRITICAL IMPORT ERROR in subconscious_hook.py: {e}. Using dummies.")
    class Config: #type:ignore
        @staticmethod
        def get_firmament_module_config(): return {"firmament_llm_role": "DUMMY_FIRMAMENT_ROLE"}
        @staticmethod
        def get_llm_config(role_name_arg):
            return {"url": "dummy_url", "model": "d_model_sh_dummy", "timeout":10.0, "temperature":0.7, "max_tokens":128} if role_name_arg=="DUMMY_FIRMAMENT_ROLE" else None
    LLMConfig = Dict[str, Any]; #type:ignore

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

logger = logging.getLogger(__name__)

def get_recent_subconscious_thoughts(limit: int = 5) -> List[Dict[str, Any]]:
    # (Full existing get_recent_subconscious_thoughts function from previous step)
    sample_thoughts_db = [
        {"content": "I wonder if Lara Croft still works at the cafe downtown. Haven't seen her in ages.","timestamp": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),"mood_at_thought": {"name": "nostalgic"}, "urgency": "low", "source":"dummy_subconscious_ Lara"},
        {"content": "I should call Bob about the project.","timestamp": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),"mood_at_thought": {"name": "focused"}, "urgency": "high", "impulse_type":"task_reminder_Bob", "source":"dummy_subconscious_Bob"},
        {"content": "Dr. Evelyn Hayes's theory on time is fascinating. I need to read more.","timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(),"mood_at_thought": {"name": "curious"},"urgency": "medium","impulse_type": "curiosity_research_Hayes","source":"dummy_subconscious_Hayes"},
        {"content": "The garden looks like it needs watering. Alice would know.","timestamp": (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(),"mood_at_thought": {"name": "observant"},"urgency": "low","source":"dummy_subconscious_Alice"},
        {"content": "A man named Victor seemed lost at the market earlier.","timestamp": (datetime.now(timezone.utc) - timedelta(minutes=25)).isoformat(),"mood_at_thought": {"name": "neutral"},"urgency": "low","source":"dummy_subconscious_Victor"}
    ]
    return sample_thoughts_db[:limit]

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

    async def main_test_subconscious_hook_llm_guidance():
        print("\n" + "="*80)
        print("Subconscious Hook Standalone Test Script (Thought Elaboration)")
        print("="*80)
        print("This script will attempt to use the configured Firmament LLM to elaborate thoughts.")
        print("Please ensure your .env file has the following variables correctly set for the")
        print("'FIRMAMENT_PRIMARY' LLM role (or the role specified in FIRMAMENT_LLM_ROLE):")
        print("  - LLM_FIRMAMENT_PRIMARY_URL:     (e.g., http://localhost:11434/v1 for Ollama)")
        print("  - LLM_FIRMAMENT_PRIMARY_MODEL:   (e.g., llama3:8b-instruct, mistral, phi3)")
        print("  - LLM_FIRMAMENT_PRIMARY_API_KEY: (e.g., 'ollama', 'lm-studio', or your actual key if required)")
        print("If these are not set, or if core Eidos components cannot be imported, this script")
        print("will fall back to using a DUMMY LLMClient or simplified elaboration.")
        print("Set logging level to DEBUG for this script's logger to see more details.")
        print("="*80 + "\n")

        # Check current LLM config that handle_thought_trigger would use
        # This requires Config to be the real one, or a dummy that mimics its structure well.
        current_fm_cfg = Config.get_firmament_module_config()
        current_llm_role = current_fm_cfg.get("firmament_llm_role", "FIRMAMENT_PRIMARY")
        current_llm_cfg = Config.get_llm_config(current_llm_role)

        is_dummy_llm_client = "dummy" in LLMClient.__name__.lower() or "dummy" in str(type(LLMClient)).lower()


        if not current_llm_cfg or not current_llm_cfg.get("url") or \
           "dummy" in current_llm_cfg.get("url", "").lower() or \
           is_dummy_llm_client:
            logger.warning("Running subconscious_hook test with DUMMY LLM configuration or DUMMY LLMClient. "
                           "Thought elaboration will be a placeholder or use raw content.\n")
        else:
            logger.info(f"Attempting REAL LLM calls for thought elaboration using role: '{current_llm_role}', "
                        f"model: '{current_llm_cfg.get('model')}', URL: '{current_llm_cfg.get('url')}'.\n")

        # Setup a mock EventBus to capture outputs of handle_thought_trigger
        _test_events_sh_main_guidance = []
        class MockEventBusSHGuidance(EventBus):
            def publish(self, event_type: str, data: dict):
                print(f"    [SubconsciousHook MainTest Capture] Event: {event_type}, Data: {str(data)[:120]}...")
                _test_events_sh_main_guidance.append({"event_type": event_type, "data": data})

        original_event_bus_sh_guidance = EventBus.instance
        EventBus.instance = lambda: MockEventBusSHGuidance()

        # Get some sample thoughts
        sample_thoughts = get_recent_subconscious_thoughts(limit=3)
        if not sample_thoughts: # pragma: no cover
            sample_thoughts = [
                {"content": "This is a default test thought if get_recent_subconscious_thoughts returns empty.",
                 "mood": "neutral", "urgency": "low", "source":"main_fallback",
                 "timestamp": datetime.now(timezone.utc).isoformat()},
                {"content": "I should really test this thoroughly.", "mood": "determined", "urgency": "medium",
                 "impulse_type": "testing_focus", "source":"main_fallback",
                 "timestamp": datetime.now(timezone.utc).isoformat()}
            ]

        for i, thought_payload in enumerate(sample_thoughts):
            print(f"--- Processing Test Thought {i+1}/{len(sample_thoughts)} ---")
            print(f"Raw thought: {thought_payload.get('content')}")
            await handle_thought_trigger(thought_payload) # Await the async handler
            print("-" * 20)
            await asyncio.sleep(0.1) # Allow any create_task in EventBus to potentially run

        print("\n--- Subconscious Hook Test Run Completed ---")
        print("Review logs above for 'LLM elaborated thought to...' messages or errors.")
        print(f"Total events captured by mock EventBus: {len(_test_events_sh_main_guidance)}")
        for evt in _test_events_sh_main_guidance:
             if evt["event_type"] == "memory.write" and evt["data"].get("type") == "thought":
                 print(f"  Logged thought content: {evt['data'].get('content')}")

        EventBus.instance = original_event_bus_sh_guidance # Restore

        # Attempt to shutdown HTTPClientManager if it was used
        if 'HTTPClientManager' in globals() and callable(globals()['HTTPClientManager'].instance):
            mgr_instance = HTTPClientManager.instance()
            # Check if it's not the dummy one from ImportError block by checking for a specific attribute
            # that the real one might have or by checking qualname of a method on the instance type.
            # This is a bit fragile. A better way would be to have a more robust way to know if it's dummy.
            is_real_http_manager = not ("dummy" in str(type(mgr_instance)).lower())

            if is_real_http_manager and hasattr(mgr_instance, 'shutdown') and asyncio.iscoroutinefunction(mgr_instance.shutdown):
                print("Attempting HTTPClientManager shutdown...")
                await mgr_instance.shutdown()


    asyncio.run(main_test_subconscious_hook_llm_guidance())
    print("\nConsider running `python -m eidos_agent.features.firmament.integrations.subconscious_hook` directly for testing.")
