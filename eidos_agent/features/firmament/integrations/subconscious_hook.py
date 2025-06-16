# eidos_agent/features/firmament/integrations/subconscious_hook.py

# This module acts as a hook or interface for triggers originating from
# the Subconscious Node (or other internal thought-provoking mechanisms).
# Its primary role is to process these triggers, potentially interact with an LLM
# to formulate a more coherent "thought", ensure this thought is
# recorded into memory via the EventBus, and then determine if the original
# trigger constitutes an actionable impulse, publishing an IMPULSE event if so.

from ..core.event_bus import EventBus
from ..core.event_types import THOUGHT_TRIGGER, IMPULSE # Added IMPULSE
from datetime import datetime, timezone
import random # Added for more varied LLM responses

# Placeholder for the LLM call
def _call_llm_for_thought_elaboration(prompt: str, mood: str = "neutral", llm_config: dict = None) -> str:
    # print(f"SubconsciousHook: _call_llm_for_thought_elaboration() invoked (placeholder)")
    # print(f"  LLM Prompt: \"{prompt}\"")
    # print(f"  Mood hint: {mood}")
    # if llm_config:
    #     print(f"  LLM Config: {llm_config}")

    response = ""
    base_prompt_content = prompt.replace("Internal monologue: ", "")

    # Enhanced LLM placeholder responses
    if "weird car" in prompt.lower() or "stalker" in prompt.lower():
        response = "That car's behavior was quite strange; it felt a bit unsettling. I should remain observant."
    elif "package" in prompt.lower() or "mail delivery" in prompt.lower():
        if mood == "excited":
            response = "A package! How exciting! I wonder what treasures it holds?"
        else:
            response = "The mail is here, and there's a package. Interesting."
    elif "should check the door locks" in base_prompt_content.lower():
        response = "A nagging feeling about the door locks again. Better to be safe than sorry and double-check."
    elif "learn a new skill" in base_prompt_content.lower():
        response = f"The idea of learning something new, like {random.choice(['coding', 'a language', 'playing an instrument'])}, is quite appealing today."
    elif "hungry" in base_prompt_content.lower() or "food" in base_prompt_content.lower():
        response = f"A rumble in my stomach. Thinking about {random.choice(['a snack', 'a proper meal', 'something delicious'])}."
    elif mood == "confused":
        response = f"My thoughts are a bit muddled regarding: \"{base_prompt_content}\". It's hard to make sense of it right now."
    elif "cloud" in prompt.lower():
        response = f"Watching the clouds drift by. It's peaceful. Makes me think about {random.choice(['the passage of time', 'the shapes they form', 'the weather later'])}."
    else:
        # Generic reflective response
        response = f"Pathos reflected on: \"{base_prompt_content}\". This sparked a sense of {mood}."

    # print(f"  LLM Response (simulated): \"{response}\"")
    return response

def handle_thought_trigger(payload: dict):
    # print(f"SubconsciousHook: handle_thought_trigger() called.")
    if not isinstance(payload, dict):
        # print("  Error: Payload for thought trigger must be a dictionary.")
        return

    raw_content = payload.get("content")
    mood_context = payload.get("mood", "neutral") # Default to neutral mood
    trigger_source = payload.get("source", "unknown_trigger_source") # Optional: track source
    urgency = payload.get("urgency", "low") # Get urgency, default to low

    if not raw_content:
        # print("  Error: 'content' (raw thought) is missing from thought trigger payload.")
        return

    # print(f"  Raw content: \"{raw_content}\", Mood: {mood_context}, Source: {trigger_source}, Urgency: {urgency}")

    # Frame the prompt for the LLM, as per design document
    llm_prompt = f"Internal monologue: {raw_content}"

    # Call the (placeholder) LLM to elaborate or refine the thought
    elaborated_thought_content = _call_llm_for_thought_elaboration(llm_prompt, mood_context)

    current_time_iso = datetime.now(timezone.utc).isoformat()
    # Prepare data for memory writing
    memory_entry = {
        "type": "thought",  # Categorizes the memory entry as a thought
        "content": elaborated_thought_content, # The LLM's response
        "raw_trigger_content": raw_content,    # Store the original trigger for context/analysis
        "mood_at_generation": mood_context,    # Mood that influenced this thought
        "source_of_trigger": trigger_source,   # Where the initial trigger came from
        "urgency_of_trigger": urgency,         # Store urgency with the thought
        "timestamp": current_time_iso          # Crucial for ordering memories
    }

    # Publish an event to write this elaborated thought to memory.
    EventBus.instance().publish("memory.write", memory_entry)
    # print(f"  Published 'memory.write' event for elaborated thought: \"{elaborated_thought_content[:60]}...\"")

    # *** NEW: Determine if this thought is an actionable impulse and publish IMPULSE event ***
    is_actionable_impulse = False
    # Keywords that might indicate an actionable intention or need.
    actionable_keywords = [
        "i should", "i need to", "maybe i can", "let's try to", "what if i",
        "i must", "i want to", "i have to", "better check", "time to"
    ]
    # Simple heuristic: check for keywords in raw_content or if urgency is high.
    # Using raw_content because it's the original unfiltered thought/stimulus.
    if any(keyword in raw_content.lower() for keyword in actionable_keywords):
        is_actionable_impulse = True
    elif urgency.lower() in ["medium", "high", "critical"]: # Making urgency check case-insensitive
        is_actionable_impulse = True

    if is_actionable_impulse:
        impulse_data = {
            # Allow a more specific 'impulse_type' if provided in the original payload,
            # otherwise, categorize based on keywords or default to 'generic'.
            "type": payload.get("impulse_type", "generic_actionable_thought"),
            "original_thought_content": raw_content,
            "elaborated_thought_content": elaborated_thought_content, # Provide LLM context
            "mood": mood_context,
            "urgency": urgency,
            "source": trigger_source, # The source of the original THOUGHT_TRIGGER
            "timestamp": current_time_iso # Use the same timestamp as the thought memory entry
        }
        # Use the IMPULSE event type string (imported from event_types)
        EventBus.instance().publish(IMPULSE, impulse_data)
        # print(f"  Published 'IMPULSE' event for: \"{raw_content[:60]}...\" (Type: {impulse_data['type']}, Urgency: {urgency})")


# This function could be registered to listen to THOUGHT_TRIGGER events
# during system initialization if the hook is event-driven.
def register_thought_trigger_handler():
    EventBus.instance().subscribe(THOUGHT_TRIGGER, handle_thought_trigger)
    # print("SubconsciousHook: Registered handle_thought_trigger with THOUGHT_TRIGGER events on the EventBus.")


if __name__ == '__main__':
    # (The existing __main__ block can be kept for testing,
    #  it will now also show IMPULSE events being published for some test cases)
    #  Ensure IMPULSE is imported or defined if __main__ test relies on it directly for MockEventBus.
    _test_published_events = [] # Store published events for verification

    # Simplified Mock EventBus for this test script
    class MockEventBusForSubconsciousHook(EventBus):
        def publish(self, event_type: str, data: dict):
            # print(f"\nMockEventBus (SubconsciousHook Test): Event '{event_type}' published.")
            # print(f"  Data: {data}")
            _test_published_events.append({"event_type": event_type, "data": data})

    # Monkey patch EventBus.instance() to use our mock for this test script
    original_event_bus_instance = EventBus.instance
    EventBus.instance = lambda: MockEventBusForSubconsciousHook()

    print("--- Testing Subconscious Hook (with Impulse Publishing Logic) ---")

    test_payloads = [
        {"content": "A car pulled into the driveway then reversed. Weird.", "mood": "confused", "source": "random_event_observer", "urgency": "low"},
        {"content": "The mailman has a package!", "mood": "excited", "urgency": "medium"},
        {"content": "I should check the door locks again!", "mood": "anxious", "urgency": "high", "impulse_type": "security_check"},
        {"content": "Maybe I can learn a new skill today.", "mood": "inspired", "urgency": "low"},
        {"content": "I'm feeling quite hungry right now.", "mood": "neutral", "urgency": "medium", "impulse_type": "hunger"},
        {"content": "Just observing the clouds. They look like fluffy sheep today.", "urgency": "low"},
        {"content": "I need to finish that report.", "mood": "stressed", "urgency": "high", "impulse_type": "task_completion"},
        {"content": "What if I called a friend?", "mood": "thoughtful", "urgency": "low"},
        "This is not a valid payload type", # Invalid payload for error handling test
        {"mood": "curious", "source": "test_harness_invalid"} # Missing content for error handling test
    ]

    for i, payload_data in enumerate(test_payloads):
        # print(f"\n--- Test Case {i+1} ---")
        if isinstance(payload_data, str):
            # print(f"Input (invalid string): {payload_data}")
            handle_thought_trigger(payload_data)
        elif isinstance(payload_data, dict):
            # print(f"Input (dict): {payload_data}")
            handle_thought_trigger(payload_data)
        else:
            # print(f"Input (unknown type): {payload_data}")
            handle_thought_trigger(payload_data) # Let the function handle it

    print("\n--- Summary of Events Published by MockEventBus ---")
    if _test_published_events:
        memory_write_count = 0
        impulse_count = 0
        for i, evt in enumerate(_test_published_events):
            event_content_key = 'content' if evt['event_type'] == "memory.write" else 'original_thought_content'
            event_content = evt['data'].get(event_content_key, '')

            print(f"Event {i+1}: Type='{evt['event_type']}', Relevant Content='{str(event_content)[:60]}...'")
            if evt['event_type'] == "memory.write":
                memory_write_count +=1
            elif evt['event_type'] == IMPULSE:
                impulse_count +=1
                print(f"    └─ Impulse Specifics: type='{evt['data'].get('type')}', urgency='{evt['data'].get('urgency')}'")
        print(f"\nTotal 'memory.write' events: {memory_write_count}")
        print(f"Total 'IMPULSE' events: {impulse_count}")
    else:
        print("No events were published.")

    # Restore original EventBus instance (good practice)
    EventBus.instance = original_event_bus_instance
    print("\n--- Subconscious Hook testing finished ---")
