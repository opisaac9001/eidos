# eidos_agent/features/firmament/integrations/subconscious_hook.py

# This module acts as a hook or interface for triggers originating from
# the Subconscious Node (or other internal thought-provoking mechanisms).
# Its primary role is to process these triggers, potentially interact with an LLM
# to formulate a more coherent "thought", and then ensure this thought is
# recorded into memory via the EventBus.

# Adjust import paths as necessary for the Eidos project structure
from ..core.event_bus import EventBus
from ..core.event_types import THOUGHT_TRIGGER # For potential subscription if hook is event-driven
# MEMORY_WRITE event type string will be used directly as per previous patterns if not in event_types explicitly for it.
# Let's assume "memory.write" is the target event string for the MemoryWriter/EthosAdapter.
# If MEMORY_WRITE = "memory.write" is in event_types.py, it could be imported.

from datetime import datetime, timezone

# Placeholder for the LLM call
def _call_llm_for_thought_elaboration(prompt: str, mood: str = "neutral", llm_config: dict = None) -> str:
    """
    Placeholder function to simulate a call to an LLM for thought elaboration.

    Args:
        prompt (str): The prompt to send to the LLM (e.g., "Internal monologue: Raw thought...").
        mood (str, optional): The mood to influence the LLM's response style. Defaults to "neutral".
        llm_config (dict, optional): Configuration for the LLM call (e.g., model name, parameters).

    Returns:
        str: The simulated elaborated thought from the LLM.
    """
    print(f"SubconsciousHook: _call_llm_for_thought_elaboration() invoked (placeholder)")
    print(f"  LLM Prompt: \"{prompt}\"")
    print(f"  Mood hint: {mood}")
    if llm_config:
        print(f"  LLM Config: {llm_config}")

    # Simulate LLM processing and response generation
    # This is highly simplified. A real LLM would provide more nuanced responses.
    if "weird car" in prompt.lower() or "stalker" in prompt.lower():
        response = "That car's behavior was quite strange; it felt a bit unsettling. I should remain observant."
    elif "package" in prompt.lower() or "mail delivery" in prompt.lower():
        if mood == "excited":
            response = "A package! How exciting! I wonder what treasures it holds?"
        else:
            response = "The mail is here, and there's a package. Interesting."
    elif mood == "confused":
        response = f"My thoughts are a bit muddled regarding: \"{prompt[19:]}\". It's hard to make sense of it right now."
    elif "cloud" in prompt.lower():
        response = f"Watching the clouds drift by. It's peaceful. Makes me think about {random.choice(['the passage of time', 'the shapes they form', 'the weather later'])}."
    else:
        # Generic reflective response
        base_prompt_content = prompt.replace("Internal monologue: ", "")
        response = f"Pathos reflected on: \"{base_prompt_content}\". This sparked a sense of {mood}."

    print(f"  LLM Response (simulated): \"{response}\"")
    return response

def handle_thought_trigger(payload: dict):
    """
    Handles a thought trigger payload, typically received from a THOUGHT_TRIGGER event
    or a direct call from an internal system like the Subconscious Node.
    It elaborates the thought using an LLM (simulated) and publishes it for memory writing.

    Args:
        payload (dict): The data associated with the thought trigger.
                        Expected to contain 'content' (the raw thought/trigger)
                        and optionally 'mood', 'urgency', 'source', etc.
    """
    print(f"SubconsciousHook: handle_thought_trigger() called.")
    if not isinstance(payload, dict):
        print("  Error: Payload for thought trigger must be a dictionary.")
        return

    raw_content = payload.get("content")
    mood_context = payload.get("mood", "neutral") # Default to neutral mood
    trigger_source = payload.get("source", "unknown_trigger_source") # Optional: track source

    if not raw_content:
        print("  Error: 'content' (raw thought) is missing from thought trigger payload.")
        return

    print(f"  Raw content: \"{raw_content}\", Mood: {mood_context}, Source: {trigger_source}")

    # Frame the prompt for the LLM, as per design document
    llm_prompt = f"Internal monologue: {raw_content}"

    # Call the (placeholder) LLM to elaborate or refine the thought
    # Potentially pass LLM configuration if available/needed
    elaborated_thought_content = _call_llm_for_thought_elaboration(llm_prompt, mood_context)

    # Prepare data for memory writing
    memory_entry = {
        "type": "thought",  # Categorizes the memory entry as a thought
        "content": elaborated_thought_content, # The LLM's response
        "raw_trigger_content": raw_content,    # Store the original trigger for context/analysis
        "mood_at_generation": mood_context,    # Mood that influenced this thought
        "source_of_trigger": trigger_source,   # Where the initial trigger came from
        "timestamp": datetime.now(timezone.utc).isoformat() # Crucial for ordering memories
    }

    # Publish an event to write this elaborated thought to memory.
    # Using "memory.write" as the event type string, assuming MemoryWriter listens to this.
    EventBus.instance().publish("memory.write", memory_entry)
    print(f"  Published 'memory.write' event for elaborated thought: \"{elaborated_thought_content[:60]}...\"")

# This function could be registered to listen to THOUGHT_TRIGGER events
# during system initialization if the hook is event-driven.
def register_thought_trigger_handler():
    EventBus.instance().subscribe(THOUGHT_TRIGGER, handle_thought_trigger)
    print("SubconsciousHook: Registered handle_thought_trigger with THOUGHT_TRIGGER events on the EventBus.")


if __name__ == '__main__':
    import random # For varied LLM responses in test

    # Setup mock EventBus for testing this module in isolation
    # This simulates the real EventBus without needing the full system.
    _test_published_events = []
    class MockEventBusForSubconsciousHook(EventBus):
        def publish(self, event_type: str, data: dict):
            print(f"\nMockEventBus (SubconsciousHook Test): Event '{event_type}' published.")
            print(f"  Data: {data}")
            _test_published_events.append({"event_type": event_type, "data": data})
            # In a real scenario, super().publish(event_type, data) would call actual subscribers.

    # Monkey patch EventBus.instance() to use our mock for this test script
    original_event_bus_instance = EventBus.instance
    EventBus.instance = lambda: MockEventBusForSubconsciousHook()

    print("--- Testing Subconscious Hook ---")

    print("\nTest 1: Thought trigger about a weird car (confused mood)")
    payload1 = {
        "content": "A car pulled into the driveway then reversed. Weird.",
        "mood": "confused",
        "source": "random_event_observer"
    }
    handle_thought_trigger(payload1)

    print("\nTest 2: Thought trigger for mail delivery (excited mood)")
    payload2 = {
        "content": "The mailman has a package!",
        "mood": "excited",
        "urgency": "medium" # Example of an extra field in payload
    }
    handle_thought_trigger(payload2)

    print("\nTest 3: Thought trigger with default mood (observing clouds)")
    payload3 = {
        "content": "Just observing the clouds. They look like fluffy sheep today."
        # No mood, should default to neutral
    }
    handle_thought_trigger(payload3)

    print("\nTest 4: Invalid payload (not a dictionary)")
    handle_thought_trigger("This is not a valid payload type")

    print("\nTest 5: Invalid payload (dictionary missing 'content')")
    handle_thought_trigger({"mood": "curious", "source": "test_harness"})

    print("\n--- Summary of Events Published by MockEventBus ---")
    if _test_published_events:
        for i, evt in enumerate(_test_published_events):
            print(f"Event {i+1}: Type='{evt['event_type']}', Content='{evt['data'].get('content', '')[:50]}...'")
    else:
        print("No events were published.")

    # Restore original EventBus instance (good practice if other tests followed in a larger suite)
    EventBus.instance = original_event_bus_instance
    print("\n--- Subconscious Hook testing finished ---")
