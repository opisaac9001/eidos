# eidos_agent/features/firmament/integrations/subconscious_hook.py

import logging # Added
import httpx # Added
# import asyncio # Not strictly needed for this version as the call is simulated

from ..core.event_bus import EventBus
from ..core.event_types import THOUGHT_TRIGGER, IMPULSE
from datetime import datetime, timezone
# Removed: import random (was for old placeholder _call_llm_for_thought_elaboration)

# Eidos core components
try:
    # Assuming this file is eidos_agent/features/firmament/integrations/subconscious_hook.py
    # Adjust path to go up three levels to eidos_agent, then to core/config.py
    from ....core.config import Config, LLMConfig
    from ....llm_integrations.llm_client import LLMClient
except ImportError as e: # Fallback for parsing if paths are tricky during dev/test # pragma: no cover
    print(f"CRITICAL IMPORT ERROR in subconscious_hook.py: Config or LLMClient not found. Error: {e}")
    class Config: # type: ignore
        @staticmethod
        def get_firmament_module_config(): return {"firmament_llm_role": "DUMMY_FIRMAMENT_ROLE"}
        @staticmethod
        def get_llm_config(role):
            if role == "DUMMY_FIRMAMENT_ROLE":
                return {"url": "dummy_url", "model": "dummy_model", "timeout": 10.0, "temperature": 0.5, "max_tokens": 50}
            return None
    LLMConfig = dict # type: ignore
    class LLMClient: # type: ignore
        constructor_takes_httpx_client = True
        def __init__(self, http_client): pass
        # Add a dummy call_llm_api for type hinting if used, though not called here
        async def call_llm_api(self, messages, llm_config, llm_role): pass # type: ignore


logger = logging.getLogger(__name__)

# Removed _call_llm_for_thought_elaboration function as its logic is now integrated below,
# and the actual LLM call is simulated differently.

def handle_thought_trigger(payload: dict):
    """
    Handles a THOUGHT_TRIGGER payload.
    It fetches Firmament's LLM configuration, constructs a prompt, and currently
    simulates an LLM call to elaborate the thought. The elaborated thought is
    then published for memory writing, and if deemed actionable, an IMPULSE event
    is also published.
    """
    logger.debug(f"SubconsciousHook: handle_thought_trigger received payload: {payload}")
    if not isinstance(payload, dict):
        logger.error("Payload for thought trigger must be a dictionary.")
        return

    raw_content = payload.get("content")
    mood_context = payload.get("mood", "neutral")
    trigger_source = payload.get("source", "unknown_trigger_source")
    urgency = payload.get("urgency", "low")

    if not raw_content:
        logger.error("'content' (raw thought) is missing from thought trigger payload.")
        return

    logger.info(f"Processing raw thought: \"{raw_content}\" (Mood: {mood_context}, Urgency: {urgency}, Source: {trigger_source})")

    # --- LLM Interaction Setup (Simulated) ---
    elaborated_thought_content = f"Default elaboration for: '{raw_content}' (Mood: {mood_context})" # Fallback

    llm_prompt = f"Internal monologue: {raw_content}"
    # messages = [{"role": "user", "content": llm_prompt}] # This would be for the actual LLM call

    firmament_module_cfg = Config.get_firmament_module_config()
    if not firmament_module_cfg: # pragma: no cover
        logger.error("Firmament module configuration not found. Cannot determine LLM role for thought elaboration.")
        # Fallback to default elaboration already set
    else:
        llm_role = firmament_module_cfg.get("firmament_llm_role", "FIRMAMENT_PRIMARY")
        firmament_llm_config: LLMConfig | None = Config.get_llm_config(llm_role)

        if firmament_llm_config:
            # logger.warning("TODO (SubconsciousHook): HTTP client in handle_thought_trigger should be shared/managed, "
            #                "not created per call. This is a placeholder for structure.")

            # In a real async implementation, an httpx.AsyncClient would be used:
            # timeout_seconds = firmament_llm_config.get("timeout", 15.0)
            # http_client = httpx.AsyncClient(timeout=timeout_seconds)
            # llm_client = LLMClient(http_client=http_client)

            logger.info(f"SIMULATING LLM call for Firmament role '{llm_role}'. Prompt (conceptual): \"{llm_prompt}\"")
            # Parameters that would be passed to llm_client.call_llm_api:
            #   messages=messages,
            #   llm_config=firmament_llm_config,
            #   llm_role=llm_role

            # New placeholder response, indicating simulation and configured role/model
            elaborated_thought_content = (
                f"Simulated LLM (Role: {llm_role}, Model: {firmament_llm_config.get('model', 'N/A')}) "
                f"elaboration for internal monologue: '{raw_content}' (Original Mood: {mood_context})"
            )
            logger.info(f"Using new placeholder LLM response: \"{elaborated_thought_content}\"")

            logger.warning("TODO (SubconsciousHook): Replace placeholder LLM response with an actual async call "
                           "to llm_client.call_llm_api. This will require making handle_thought_trigger async "
                           "and ensuring the EventBus and its subscribers can handle async operations "
                           "(e.g., by using asyncio.create_task for dispatching to async handlers from a sync bus, "
                           "or by upgrading EventBus to be fully async).")
            # logger.warning("TODO (SubconsciousHook): If an httpx.AsyncClient is created here per call (which is not ideal), "
            #                "it must be properly closed using 'async with' or 'await http_client.aclose()'. "
            #                "This is not done currently as the handler is synchronous and the call is simulated. "
            #                "The preferred solution is a shared/managed HTTP client instance.")
        else: # pragma: no cover
            logger.error(f"LLM configuration for Firmament role '{llm_role}' not found. Using default elaboration.")

    # --- Event Publishing Logic (remains mostly the same, uses new elaborated_thought_content) ---
    current_time_iso = datetime.now(timezone.utc).isoformat()
    memory_entry = {
        "type": "thought",
        "content": elaborated_thought_content,
        "raw_trigger_content": raw_content,
        "mood_at_generation": mood_context,
        "source_of_trigger": trigger_source,
        "urgency_of_trigger": urgency,
        "timestamp": current_time_iso
    }
    EventBus.instance().publish("memory.write", memory_entry)

    is_actionable_impulse = False
    actionable_keywords = [
        "i should", "i need to", "maybe i can", "let's try to", "what if i",
        "i must", "i want to", "i have to", "better check", "time to"
    ]
    if any(keyword in raw_content.lower() for keyword in actionable_keywords) or \
       urgency.lower() in ["medium", "high", "critical"]:
        is_actionable_impulse = True

    if is_actionable_impulse:
        impulse_data = {
            "type": payload.get("impulse_type", "generic_actionable_thought"),
            "original_thought_content": raw_content,
            "elaborated_thought_content": elaborated_thought_content, # Include the (simulated) LLM elaboration
            "mood": mood_context,
            "urgency": urgency,
            "source": trigger_source,
            "timestamp": current_time_iso
        }
        EventBus.instance().publish(IMPULSE, impulse_data)

def register_thought_trigger_handler():
    """Subscribes handle_thought_trigger to THOUGHT_TRIGGER events on the EventBus."""
    EventBus.instance().subscribe(THOUGHT_TRIGGER, handle_thought_trigger)
    # logger.info("SubconsciousHook: Registered handle_thought_trigger for THOUGHT_TRIGGER events.")


if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    _test_published_events = []

    # Using a simplified EventBus mock for this __main__ as the focus is on handle_thought_trigger's internal logic
    class MockEventBusForSubconsciousHookTest(EventBus):
        def publish(self, event_type: str, data: dict):
            print(f"    [MockEventBus Capture] Event: {event_type}, Data: {str(data)[:120]}...")
            _test_published_events.append({"event_type": event_type, "data": data})

    original_event_bus_instance = EventBus.instance
    EventBus.instance = lambda: MockEventBusForSubconsciousHookTest() # Patch with the simple mock

    print("--- Testing Subconscious Hook (with SIMULATED LLMClient structure and new placeholder response) ---")

    test_payloads_for_llm_sim = [
        {"content": "I should check the door locks again!", "mood": "anxious", "urgency": "high", "impulse_type": "security_check"},
        {"content": "Maybe I can learn a new skill today, like painting.", "mood": "inspired", "urgency": "low"},
        {"content": "The sky is very dark; it might rain soon.", "mood": "observant", "urgency": "low"},
    ]

    # Simulate a Firmament LLM config being available
    # This would normally be loaded from Config.LLM by Config.get_llm_config()
    mock_firmament_llm_config = {
        "url": "http://mockhost:1234/v1",
        "model": "firmament-test-model-v1",
        "api_key": "mock_key",
        "temperature": 0.55,
        "timeout": 12.0,
        "max_tokens": 1000
    }

    # Patch Config.get_llm_config to return our mock config when FIRMAMENT_PRIMARY is requested
    # And Config.get_firmament_module_config to specify FIRMAMENT_PRIMARY as the role
    with patch('eidos_agent.core.config.Config.get_llm_config', side_effect=lambda role: mock_firmament_llm_config if role == "FIRMAMENT_PRIMARY" else None) as mock_get_llm_config, \
         patch('eidos_agent.core.config.Config.get_firmament_module_config', return_value={"firmament_llm_role": "FIRMAMENT_PRIMARY"}) as mock_get_firmament_cfg:

        for i, payload in enumerate(test_payloads_for_llm_sim):
            print(f"\n--- Test Case {i+1} ---")
            print(f"Input Payload: {payload}")
            _test_published_events.clear() # Clear for each payload
            handle_thought_trigger(payload)

            print("  Published events for this case:")
            for evt in _test_published_events:
                event_content_key = 'content' if evt['event_type'] == "memory.write" else 'original_thought_content'
                event_content = evt['data'].get(event_content_key, '')
                print(f"    - Type='{evt['event_type']}', Relevant Content='{str(event_content)[:70]}...'")
                if evt['event_type'] == "memory.write" and evt['data'].get('type') == 'thought':
                    assert "Simulated LLM (Role: FIRMAMENT_PRIMARY" in evt['data']['content'], \
                        f"Elaborated thought content does not indicate simulation with correct role. Got: {evt['data']['content']}"
                    assert mock_firmament_llm_config['model'] in evt['data']['content'], \
                        f"Elaborated thought content does not mention the (mocked) model name. Got: {evt['data']['content']}"

            # Verify that get_llm_config was called with the expected role
            mock_get_llm_config.assert_any_call("FIRMAMENT_PRIMARY")


    EventBus.instance = original_event_bus_instance # Restore
    print("\n--- Subconscious Hook (simulated LLM) testing finished ---")
