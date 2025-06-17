# eidos_agent/features/firmament/integrations/subconscious_hook.py

import logging
import httpx
from typing import List, Dict, Any, Optional # Added List, Dict, Any, Optional

from ..core.event_bus import EventBus
from ..core.event_types import THOUGHT_TRIGGER, IMPULSE
from datetime import datetime, timezone, timedelta # Added timedelta

# Eidos core components
try:
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
    LLMConfig = Dict[str, Any] # type: ignore
    class LLMClient: # type: ignore
        constructor_takes_httpx_client = True
        def __init__(self, http_client): pass
        async def call_llm_api(self, messages, llm_config, llm_role): pass # type: ignore

logger = logging.getLogger(__name__)

# --- New Function: Simulated SubconsciousNode Data Source ---
def get_recent_subconscious_thoughts(limit: int = 5) -> List[Dict[str, Any]]:
    """
    Simulates fetching recent thoughts from the SubconsciousNode.
    Each thought dictionary should ideally contain 'content', 'timestamp',
    'mood_at_thought', 'urgency', and optionally 'impulse_type'.

    TODO: Replace this with actual integration with SubconsciousNode logs/API.
          This might involve querying a database, an API endpoint, or reading logs.
    """
    # logger.info(f"Simulating fetch of {limit} recent subconscious thoughts.")
    # Static list of sample thoughts for consistent testing and demonstration.
    # More thoughts are defined than the default limit to allow testing `limit`.
    sample_thoughts_db = [
        {
            "content": "I wonder if Lara Croft still works at the cafe downtown. Haven't seen her in ages.",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=5, seconds=10)).isoformat(),
            "mood_at_thought": {"name": "nostalgic", "intensity": 0.6, "dominant_emotion": "longing"},
            "urgency": "low",
            "source": "subconscious_memory_retrieval" # Example source
        },
        {
            "content": "Need to remember to call Bob about the upcoming project deadline. It's critical.",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=10, seconds=25)).isoformat(),
            "mood_at_thought": {"name": "focused", "intensity": 0.8, "dominant_emotion": "anxiety"},
            "urgency": "high", # Higher urgency
            "impulse_type": "task_reminder", # Specific type for subconscious_hook to pass to IMPULSE
            "source": "subconscious_goal_monitoring"
        },
        {
            "content": "That mention of Dr. Evelyn Hayes in the news article about quantum entanglement was interesting. I should look her up.",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=15, seconds=50)).isoformat(),
            "mood_at_thought": {"name": "curious", "intensity": 0.7, "dominant_emotion": "intrigue"},
            "urgency": "medium", # Medium urgency due to "should look her up"
            "impulse_type": "curiosity_research",
            "source": "subconscious_information_processing"
        },
        {
            "content": "Pathos should consider what Alice said about the garden's soil pH. It might explain the wilting roses.", # Known NPC, self-reference for Pathos
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=20, seconds=15)).isoformat(),
            "mood_at_thought": {"name": "reflective", "intensity": 0.5, "dominant_emotion": "contemplation"},
            "urgency": "low",
            "source": "subconscious_problem_solving"
        },
        {
            "content": "A man named Victor was asking for directions earlier near the library. He seemed lost.",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=25, seconds=33)).isoformat(),
            "mood_at_thought": {"name": "neutral", "intensity": 0.4, "dominant_emotion": "observation"},
            "urgency": "low",
            "source": "subconscious_sensory_log_echo"
        },
        {
            "content": "The weather is surprisingly pleasant today. Maybe I can go for a walk.",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=30, seconds=5)).isoformat(),
            "mood_at_thought": {"name": "content", "intensity": 0.6, "dominant_emotion": "pleasantness"},
            "urgency": "low",
            "impulse_type": "leisure_activity_suggestion",
            "source": "subconscious_environmental_awareness"
        },
        {
            "content": "I'm feeling quite hungry. That pizza from last night sounds good.",
            "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=35, seconds=12)).isoformat(),
            "mood_at_thought": {"name": "anticipatory", "intensity": 0.5, "dominant_emotion": "craving"},
            "urgency": "medium",
            "impulse_type": "hunger",
            "source": "subconscious_physiological_monitoring"
        }
    ]
    # Return a slice of the most recent 'limit' thoughts.
    # The list is ordered with most recent first if it were a real DB query.
    # For this static list, it's just the first `limit` items.
    return sample_thoughts_db[:limit]


def handle_thought_trigger(payload: dict):
    """
    Handles a THOUGHT_TRIGGER payload.
    It fetches Firmament's LLM configuration, constructs a prompt, and currently
    simulates an LLM call to elaborate the thought. The elaborated thought is
    then published for memory writing, and if deemed actionable, an IMPULSE event
    is also published.
    """
    # logger.debug(f"SubconsciousHook: handle_thought_trigger received payload: {payload}")
    if not isinstance(payload, dict):
        logger.error("Payload for thought trigger must be a dictionary.")
        return

    raw_content = payload.get("content")
    mood_context = payload.get("mood", payload.get("mood_at_thought", "neutral")) # Use mood_at_thought as fallback
    if isinstance(mood_context, dict): # If mood is a dict, extract name
        mood_context = mood_context.get("name", "neutral")

    trigger_source = payload.get("source", "unknown_trigger_source")
    urgency = payload.get("urgency", "low")

    if not raw_content:
        logger.error("'content' (raw thought) is missing from thought trigger payload.")
        return

    # logger.info(f"Processing raw thought: \"{raw_content}\" (Mood: {mood_context}, Urgency: {urgency}, Source: {trigger_source})")

    elaborated_thought_content = f"Default elaboration for: '{raw_content}' (Mood: {mood_context})"

    llm_prompt = f"Internal monologue: {raw_content}"

    firmament_module_cfg = Config.get_firmament_module_config()
    if not firmament_module_cfg: # pragma: no cover
        logger.error("Firmament module configuration not found. Cannot determine LLM role for thought elaboration.")
    else:
        llm_role = firmament_module_cfg.get("firmament_llm_role", "FIRMAMENT_PRIMARY")
        firmament_llm_config: LLMConfig | None = Config.get_llm_config(llm_role)

        if firmament_llm_config:
            # logger.info(f"SIMULATING LLM call for Firmament role '{llm_role}'. Prompt (conceptual): \"{llm_prompt}\"")
            elaborated_thought_content = (
                f"Simulated LLM (Role: {llm_role}, Model: {firmament_llm_config.get('model', 'N/A')}) "
                f"elaboration for internal monologue: '{raw_content}' (Original Mood: {mood_context})"
            )
            # logger.info(f"Using new placeholder LLM response: \"{elaborated_thought_content}\"")
            logger.warning("TODO (SubconsciousHook): Replace placeholder LLM response with an actual async call.")
        else: # pragma: no cover
            logger.error(f"LLM configuration for Firmament role '{llm_role}' not found. Using default elaboration.")

    current_time_iso = payload.get("timestamp", datetime.now(timezone.utc).isoformat()) # Use original thought timestamp if available
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
        "i must", "i want to", "i have to", "better check", "time to", "remember to"
    ]
    if any(keyword in raw_content.lower() for keyword in actionable_keywords) or \
       urgency.lower() in ["medium", "high", "critical"]:
        is_actionable_impulse = True

    if is_actionable_impulse:
        impulse_data = {
            "type": payload.get("impulse_type", "generic_actionable_thought"),
            "original_thought_content": raw_content,
            "elaborated_thought_content": elaborated_thought_content,
            "mood": mood_context,
            "urgency": urgency,
            "source": trigger_source, # Source of the THOUGHT_TRIGGER payload
            "timestamp": current_time_iso # Timestamp of the original thought
        }
        EventBus.instance().publish(IMPULSE, impulse_data)

def register_thought_trigger_handler():
    """Subscribes handle_thought_trigger to THOUGHT_TRIGGER events on the EventBus."""
    EventBus.instance().subscribe(THOUGHT_TRIGGER, handle_thought_trigger)
    # logger.info("SubconsciousHook: Registered handle_thought_trigger for THOUGHT_TRIGGER events.")


if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger_sh = logging.getLogger('eidos_agent.features.firmament.integrations.subconscious_hook')
    logger_sh.setLevel(logging.DEBUG) # Enable debug for this module to see more logs

    logger.info("--- Testing Subconscious Hook ---")

    # --- Test the new get_recent_subconscious_thoughts function ---
    print("\n--- Testing get_recent_subconscious_thoughts ---")
    recent_thoughts_data = get_recent_subconscious_thoughts(limit=3)
    print(f"Fetched {len(recent_thoughts_data)} recent thoughts:")
    for i, thought_info in enumerate(recent_thoughts_data):
        mood_info = thought_info.get('mood_at_thought', {})
        mood_name = mood_info.get('name', 'N/A') if isinstance(mood_info, dict) else 'N/A'
        print(f"  Thought {i+1}: '{thought_info['content']}' (Mood: {mood_name}, Urgency: {thought_info.get('urgency')})")
    assert len(recent_thoughts_data) == 3, f"Expected 3 thoughts, got {len(recent_thoughts_data)}"
    if recent_thoughts_data: # Check content if list is not empty
        assert "Lara Croft" in recent_thoughts_data[0]["content"], "First thought content mismatch"

    print("\n--- Testing handle_thought_trigger (using one of the fetched thoughts) ---")
    _test_published_events_main = []
    # Using a simplified EventBus mock for this __main__
    class MockEventBusForMainTest(EventBus):
        def publish(self, event_type: str, data: dict):
            print(f"    [MockEventBus MainTest Capture] Event: {event_type}, Data: {str(data)[:120]}...")
            _test_published_events_main.append({"event_type": event_type, "data": data})

    original_event_bus_instance_main = EventBus.instance
    EventBus.instance = lambda: MockEventBusForMainTest() # Patch with the simple mock

    # Use a thought that should trigger an impulse (e.g., the one about Bob or Dr. Hayes)
    if len(recent_thoughts_data) > 1:
        actionable_thought_payload = recent_thoughts_data[1] # "Need to remember to call Bob..."
        print(f"\nProcessing actionable thought for handle_thought_trigger: {actionable_thought_payload}")
        handle_thought_trigger(actionable_thought_payload)

        found_memory_write_main = any(e["event_type"] == "memory.write" for e in _test_published_events_main)
        found_impulse_main = any(e["event_type"] == IMPULSE for e in _test_published_events_main)
        assert found_memory_write_main, "Memory.write event not found in __main__ test for actionable thought"
        assert found_impulse_main, "IMPULSE event not found in __main__ test for actionable thought"
        if found_impulse_main:
            impulse_event = next(e for e in _test_published_events_main if e["event_type"] == IMPULSE)
            assert impulse_event["data"]["type"] == "task_reminder", f"Expected impulse_type 'task_reminder', got {impulse_event['data']['type']}"
        print("handle_thought_trigger test with actionable thought produced expected event types.")
    else:
        print("Skipping handle_thought_trigger test as not enough thoughts were fetched.")

    EventBus.instance = original_event_bus_instance_main # Restore
    logger.info("--- Subconscious Hook __main__ testing finished ---")
