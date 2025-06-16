# eidos_agent/features/firmament/core/event_handlers/impulse.py
from ..event_bus import EventBus
from ..event_types import IMPULSE, SLEEP_REQUESTED
from datetime import datetime, timedelta, timezone # Added timezone
import re # For topic extraction

# Define new event type strings (could be moved to event_types.py later if they become widely used)
EVENT_MEMORY_WRITE = "memory.write"
EVENT_REQUEST_FOOD_PREP = "world.request_food_prep" # Example custom event
EVENT_LOGOS_RESEARCH_REQUEST = "logos.research_request" # Example custom event

def _log_action_to_memory(action_description: str, impulse_data: dict, specific_metadata: dict = None):
    """Helper function to publish a memory.write event for actions taken due to impulses."""
    timestamp_utc = datetime.now(timezone.utc).isoformat()
    # Ensure impulse_data is a dict before trying to .get() from it
    if not isinstance(impulse_data, dict):
        impulse_data = {} # Default to empty dict if not a dict

    memory_entry = {
        "type": "impulse_response_action",
        "content": action_description,
        "metadata": {
            "triggering_impulse_type": impulse_data.get("type", "generic"),
            "triggering_original_thought": impulse_data.get("original_thought_content"),
            "triggering_elaborated_thought": impulse_data.get("elaborated_thought_content"),
            "triggering_mood": impulse_data.get("mood"),
            "triggering_urgency": impulse_data.get("urgency"),
            "triggering_timestamp": impulse_data.get("timestamp"), # Timestamp of the impulse itself
            "action_timestamp_utc": timestamp_utc # Timestamp of this action
        }
    }
    if specific_metadata:
        memory_entry["metadata"].update(specific_metadata)

    EventBus.instance().publish(EVENT_MEMORY_WRITE, memory_entry)
    # print(f"  Logged action to memory: {action_description}")

def handle_impulse(data: dict):
    """
    Handles impulse events. The 'data' dict is expected to match
    the impulse_data payload from subconscious_hook.py.
    Expected keys in data: "type", "original_thought_content", "elaborated_thought_content",
                           "mood", "urgency", "source", "timestamp".
    """
    # print(f"ImpulseHandler: Received impulse: {data}")
    if not isinstance(data, dict):
        # print("  Error: Impulse data must be a dictionary.")
        _log_action_to_memory("Error: Received invalid impulse data (not a dict).", data)
        return

    impulse_type = data.get("type", "generic").lower()
    original_thought = data.get("original_thought_content", "")
    urgency = data.get("urgency", "low").lower()
    action_taken = False
    action_description = ""

    # Tired Impulse
    if impulse_type == "tired" or \
       any(kw in original_thought.lower() for kw in ["tired", "sleepy", "exhausted", "i need to sleep"]):

        sleep_start_time = datetime.now(timezone.utc) + timedelta(minutes=random.randint(15, 60)) # Randomize sleep start slightly
        event_data_sleep = {
            "reason": "tired_impulse_response",
            "requester": "firmament.impulse_handler",
            "start_time_utc": sleep_start_time.isoformat(),
            "original_impulse_data_summary": { # Avoid circular refs by summarizing
                "type": data.get("type"), "urgency": data.get("urgency")
            }
        }
        EventBus.instance().publish(SLEEP_REQUESTED, event_data_sleep)
        action_description = f"Responded to '{impulse_type}' impulse by requesting sleep. Sleep scheduled around {sleep_start_time.isoformat()} UTC."
        _log_action_to_memory(action_description, data, {"sleep_request_details": {"start_time": sleep_start_time.isoformat()}})
        action_taken = True

    # Hunger Impulse
    elif impulse_type == "hunger" or \
         any(kw in original_thought.lower() for kw in ["hungry", "food", "eat", "starving", "famished", "rumble"]):

        food_request_payload = {
            "urgency": urgency,
            "dietary_preferences": data.get("dietary_preferences", "any"),
            "trigger_timestamp": data.get("timestamp"),
            "original_impulse_data_summary": {
                "type": data.get("type"), "urgency": data.get("urgency")
            }
        }
        EventBus.instance().publish(EVENT_REQUEST_FOOD_PREP, food_request_payload)
        action_description = f"Responded to '{impulse_type}' ({urgency}) impulse by requesting food preparation."
        _log_action_to_memory(action_description, data, {"food_request_details": {"urgency": urgency}})
        action_taken = True

    # Curiosity Impulse
    elif impulse_type == "curiosity" or \
         any(kw in original_thought.lower() for kw in ["learn about", "what is", "research", "wonder about", "curious about", "find out about"]):

        topic = original_thought # Default topic to the whole thought
        # Try to extract a more specific topic using regex
        # Looks for phrases like "learn about X", "what is X", "research X"
        match = re.search(r"(?:learn about|what is|research|wonder about|curious about|find out about)\s+([^.?!\n]+)", original_thought, re.IGNORECASE)
        if match and match.group(1):
            topic = match.group(1).strip().rstrip('?.!') # Clean up extracted topic

        research_request_payload = {
            "query_topic": topic,
            "urgency": urgency,
            "requested_by": "firmament.impulse_handler",
            "trigger_timestamp": data.get("timestamp"),
            "original_impulse_data_summary": {
                "type": data.get("type"), "urgency": data.get("urgency")
            }
        }
        EventBus.instance().publish(EVENT_LOGOS_RESEARCH_REQUEST, research_request_payload)
        action_description = f"Responded to '{impulse_type}' ({urgency}) impulse by initiating research on topic: '{topic}'."
        _log_action_to_memory(action_description, data, {"research_request_details": {"topic": topic}})
        action_taken = True

    # Fallback for specific but unhandled impulse types
    if not action_taken and impulse_type not in ["generic", "generic_actionable_thought"]:
        action_description = f"Acknowledged a '{impulse_type}' impulse of '{urgency}' urgency. No specific automated action is predefined for this type yet."
        _log_action_to_memory(action_description, data)
        action_taken = True # Action taken is logging the acknowledgement

    # Optionally, log if a generic impulse didn't trigger any specific handler (if needed for debugging)
    # if not action_taken:
    #     # print(f"  Impulse type '{impulse_type}' with content '{original_thought}' did not trigger a specific action.")
    #     pass


if __name__ == '__main__':
    import random # For sleep time randomization in test
    _test_events_captured = [] # To store (event_name, data) tuples

    # Clear EventBus subscribers for a clean test run
    if hasattr(EventBus, "_instance") and EventBus._instance:
        EventBus.instance()._subscribers.clear()

    bus = EventBus.instance() # Get a fresh instance or clear one

    # Define a generic capture handler that knows its event name
    def create_capture_handler(event_name_to_capture):
        def handler(data):
            # print(f"    [TestCapture] Event: {event_name_to_capture}, Data: {str(data)[:150]}...")
            _test_events_captured.append({"event_name": event_name_to_capture, "data": data})
        return handler

    # Subscribe handlers
    bus.subscribe(IMPULSE, handle_impulse) # The handler under test
    bus.subscribe(SLEEP_REQUESTED, create_capture_handler(SLEEP_REQUESTED))
    bus.subscribe(EVENT_MEMORY_WRITE, create_capture_handler(EVENT_MEMORY_WRITE))
    bus.subscribe(EVENT_REQUEST_FOOD_PREP, create_capture_handler(EVENT_REQUEST_FOOD_PREP))
    bus.subscribe(EVENT_LOGOS_RESEARCH_REQUEST, create_capture_handler(EVENT_LOGOS_RESEARCH_REQUEST))

    print("--- Testing Impulse Handler (Enhanced) ---")
    base_timestamp = datetime.now(timezone.utc)
    test_impulses = [
        {"type": "tired", "original_thought_content": "I'm so sleepy, I really need to sleep.", "urgency": "high", "timestamp": (base_timestamp - timedelta(seconds=30)).isoformat()},
        {"type": "hunger", "original_thought_content": "I could really eat a horse right now.", "urgency": "medium", "mood": "cranky", "timestamp": (base_timestamp - timedelta(seconds=20)).isoformat()},
        {"type": "curiosity", "original_thought_content": "I wonder about the history of the internet.", "urgency": "low", "timestamp": (base_timestamp - timedelta(seconds=10)).isoformat()},
        {"type": "generic_actionable_thought", "original_thought_content": "The sky is blue today.", "urgency": "low", "timestamp": base_timestamp.isoformat()}, # Generic but was actionable
        {"type": "custom_unhandled_impulse", "original_thought_content": "This is a test of an unhandled specific impulse type.", "urgency": "low", "timestamp": (base_timestamp + timedelta(seconds=10)).isoformat()},
        {"type": "curiosity_phrased_differently", "original_thought_content": "Maybe I should learn about black holes in astrophysics.", "urgency": "medium", "timestamp": (base_timestamp + timedelta(seconds=20)).isoformat()},
        {"type": "generic", "original_thought_content": "A generic, non-actionable thought.", "urgency": "low", "timestamp": (base_timestamp + timedelta(seconds=30)).isoformat()}, # Truly generic, no specific handler
        {"type": "invalid_data_test", "original_thought_content": None} # Test robustness
    ]

    all_tests_passed = True
    for i, impulse_payload in enumerate(test_impulses):
        _test_events_captured.clear() # Clear captures for each test case
        print(f"\n--- Test Case {i+1}: Publishing IMPULSE for: \"{impulse_payload.get('original_thought_content', 'No content')}\" (Type: {impulse_payload.get('type')}) ---")
        bus.publish(IMPULSE, impulse_payload)

        print(f"  Captured events for Test Case {i+1} ({len(_test_events_captured)} total):")
        # It's guaranteed that at least one MEMORY_WRITE event occurs if data is valid (for acknowledgement or action)
        has_memory_write = any(e["event_name"] == EVENT_MEMORY_WRITE for e in _test_events_captured)

        # Log captured events for debugging
        for cap_event in _test_events_captured:
            relevant_data = cap_event['data'].get('content',
                                                cap_event['data'].get('reason',
                                                                    cap_event['data'].get('query_topic',
                                                                                        str(cap_event['data']) # fallback to full data string
                                                                                        )))
            print(f"    - {cap_event['event_name']}: {str(relevant_data)[:100]}...")

        # Basic assertions based on expected outcomes
        try:
            if not isinstance(impulse_payload.get("original_thought_content"), str) and impulse_payload.get("type") == "invalid_data_test": # Special case for robustness test
                 assert has_memory_write and "Error: Received invalid impulse data" in _test_events_captured[0]['data']['content']
            elif impulse_payload.get("type") == "tired" or "sleepy" in impulse_payload.get("original_thought_content","").lower():
                assert any(e["event_name"] == SLEEP_REQUESTED for e in _test_events_captured), f"SLEEP_REQUESTED not fired for 'tired'"
                assert has_memory_write and "requesting sleep" in _test_events_captured[0]['data']['content'], "Memory write for tired missing or incorrect"
            elif impulse_payload.get("type") == "hunger" or any(kw in impulse_payload.get("original_thought_content","").lower() for kw in ["hungry", "eat a horse"]):
                assert any(e["event_name"] == EVENT_REQUEST_FOOD_PREP for e in _test_events_captured), "REQUEST_FOOD_PREP not fired for 'hunger'"
            elif impulse_payload.get("type", "").startswith("curiosity") or "wonder about" in impulse_payload.get("original_thought_content","").lower() or "learn about black holes" in impulse_payload.get("original_thought_content","").lower():
                assert any(e["event_name"] == EVENT_LOGOS_RESEARCH_REQUEST for e in _test_events_captured), "LOGOS_RESEARCH_REQUEST not fired for 'curiosity'"
                if "black holes" in impulse_payload.get("original_thought_content",""):
                    assert any(e["data"].get("query_topic") == "black holes in astrophysics" for e in _test_events_captured if e["event_name"] == EVENT_LOGOS_RESEARCH_REQUEST), "Topic extraction failed for black holes"
            elif impulse_payload.get("type") == "custom_unhandled_impulse":
                assert has_memory_write and "Acknowledged" in _test_events_captured[0]['data']['content'] and "custom_unhandled_impulse" in _test_events_captured[0]['data']['content'], "Memory write for unhandled specific type missing/incorrect"
            elif impulse_payload.get("type") == "generic_actionable_thought": # This was actionable in subconscious_hook
                 assert has_memory_write and "Acknowledged" in _test_events_captured[0]['data']['content'] and "generic_actionable_thought" in _test_events_captured[0]['data']['content'], "Memory write for generic_actionable_thought missing/incorrect"
            elif impulse_payload.get("type") == "generic": # Truly generic, no specific action, so no specific event apart from memory log
                 assert not any(e["event_name"] not in [IMPULSE, EVENT_MEMORY_WRITE] for e in _test_events_captured), "Generic impulse should not fire action events"
                 assert not has_memory_write, "Truly generic impulse should not have action logged by default" # Corrected: generic non-actionable should NOT log action.

            print(f"  Test Case {i+1} PASSED specific assertions.")
        except AssertionError as e:
            print(f"  Test Case {i+1} FAILED: {e}")
            all_tests_passed = False

    print(f"\n--- Impulse Handler testing finished. All main assertions passed: {all_tests_passed} ---")
