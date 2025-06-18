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

            system_prompt_elaborate = "You are an internal monologue elaborator. Take the user's raw thought and expand on it slightly, maintaining the original mood and intent, as if it's Pathos's own internal continuation of the thought. Keep it concise, 1-3 sentences. Do not be conversational or add preambles like 'Okay, here's an elaboration'. Directly provide the elaborated thought text only."
            user_prompt_elaborate = f"Internal monologue: {raw_content}\nMood context: {mood_context}"
            messages = [
                {"role": "system", "content": system_prompt_elaborate},
                {"role": "user", "content": user_prompt_elaborate}
            ]
            logger.info(f"SubconsciousHook: Calling LLM (Role: {llm_role}, Model: {firmament_llm_config.get('model','N/A')}) for thought elaboration.")

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
                    logger.error(f"SubconsciousHook: LLM API error during thought elaboration: {llm_error_detail}")
                elif not full_response_str.strip():
                    logger.warning(f"SubconsciousHook: LLM returned empty elaboration for '{raw_content}'. Using raw_content as fallback.")
                else:
                    elaborated_thought_content = full_response_str.strip() # Use LLM response
                    logger.info(f"SubconsciousHook: LLM elaborated thought for '{raw_content}' to '{elaborated_thought_content}'")
            except Exception as e: # pragma: no cover
                logger.error(f"SubconsciousHook: Error calling LLM for thought elaboration: {e}", exc_info=True)
                # Fallback to raw_content is already set
        else: # pragma: no cover
            logger.error("SubconsciousHook: Failed to get shared HTTP client for thought elaboration. Using raw content.")
    else:
        logger.warning(f"SubconsciousHook: LLM config for role '{llm_role}' not found or URL missing. Using raw content for elaboration.")

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
    logging.basicConfig(level=logging.DEBUG)
    logger_sh_main = logging.getLogger('eidos_agent.features.firmament.integrations.subconscious_hook')
    logger_sh_main.setLevel(logging.DEBUG)

    async def main_test_subconscious_hook_async():
        logger_sh_main.info("--- Testing Subconscious Hook (Async Handler & LLM Call Structure) ---")

        _test_events_sh_main_async = []
        class MockEventBusForSHAsync(EventBus):
            def publish(self, event_type: str, data: dict):
                print(f"    [MockEventBusSHAsync Capture] Event: {event_type}, Data: {str(data)[:120]}...")
                _test_events_sh_main_async.append({"event_type":event_type, "data":data})

        original_event_bus_sh_async = EventBus.instance
        EventBus.instance = lambda: MockEventBusForSHAsync() #type:ignore

        # This test will use the DUMMY LLMClient if actual imports failed,
        # or a real one if imports succeeded and .env is configured for FIRMAMENT_PRIMARY.
        # The dummy LLMClient yields a predefined JSON-like string.

        sample_thought_payload = get_recent_subconscious_thoughts(limit=3)[2] # Dr. Evelyn Hayes thought
        sample_thought_payload['content'] = "I should definitely research Dr. Evelyn Hayes's theory on time more deeply."
        sample_thought_payload['impulse_type'] = "deep_research_needed"
        sample_thought_payload['urgency'] = "high"


        logger_sh_main.info(f"Processing thought for async handler: {sample_thought_payload['content']}")
        await handle_thought_trigger(sample_thought_payload) # Await the async handler

        logger_sh_main.info(f"Captured events ({len(_test_events_sh_main_async)} total):")
        found_memory_write_sh = False
        found_impulse_sh = False
        for evt_sh in _test_events_sh_main_async:
            logger_sh_main.info(f"  - Type: {evt_sh['event_type']}, "
                                f"Content/Trigger: {str(evt_sh['data'].get('content', evt_sh['data'].get('original_thought_content')))[:70]}")
            if evt_sh["event_type"] == "memory.write" and evt_sh["data"]["type"] == "thought":
                found_memory_write_sh = True
                # Check if elaboration happened (dummy or real)
                assert evt_sh["data"]["content"] != sample_thought_payload["content"] or "dummy LLM elaboration" in evt_sh["data"]["content"], \
                    f"Elaborated thought content missing or same as raw. Got: {evt_sh['data']['content']}"
            if evt_sh["event_type"] == IMPULSE and evt_sh["data"]["type"] == "deep_research_needed":
                found_impulse_sh = True

        assert found_memory_write_sh, "Memory.write (thought) event not found in __main__ async test"
        assert found_impulse_sh, "IMPULSE event (type 'deep_research_needed') not found in __main__ async test"
        logger_sh_main.info("Subconscious hook async handler test completed. Check logs for LLM call details or dummy responses.")

        # Test HTTPClientManager shutdown if it was used by a real LLMClient
        if 'HTTPClientManager' in globals() and callable(globals()['HTTPClientManager'].instance) and \
           not ("dummy" in str(type(HTTPClientManager.instance())).lower()): # Check if not dummy
            logger_sh_main.info("Attempting HTTPClientManager shutdown...")
            shared_manager_instance_sh = HTTPClientManager.instance()
            if hasattr(shared_manager_instance_sh, 'shutdown') and asyncio.iscoroutinefunction(shared_manager_instance_sh.shutdown):
                 await shared_manager_instance_sh.shutdown()
                 logger_sh_main.info("Shared HTTPClientManager shutdown called successfully.")

        EventBus.instance = original_event_bus_sh_async # Restore

    asyncio.run(main_test_subconscious_hook_async())
    print("\n--- Subconscious Hook __main__ (async handler) testing finished ---")
