# Adjust import paths as necessary for the Eidos project structure
from ..event_bus import EventBus
from ..event_types import WORLD_EVENT, THOUGHT_TRIGGER
import random

EVENT_POOL = ["car_driveby", "mail_delivery", "stranger_dog_barks", "birds_chirping", "distant_siren"]

def maybe_trigger_random_event(data=None): # Added data argument with default for consistency
    """
    May trigger a random world event based on a probability.
    If an event is triggered, it's published on the EventBus.
    Some events might also trigger secondary events like thoughts.
    """
    # The 'data' argument is included for consistency with other event handlers,
    # though this specific function might often be called without specific event data
    # (e.g., on a timer or a general simulation tick).
    if data:
        print(f"maybe_trigger_random_event called with data: {data}")
    else:
        print("maybe_trigger_random_event called without data.")

    if random.random() < 0.2: # Example probability: 20% chance to trigger an event
        selected_event = random.choice(EVENT_POOL)
        event_data = {"type": "random_world_event", "event_name": selected_event, "source": "firmament.random_events"}

        EventBus.instance().publish(WORLD_EVENT, event_data)
        print(f"Published {WORLD_EVENT}: {event_data}")

        # Example conditional logic based on the triggered event
        if selected_event == "car_driveby":
            thought_content = "A car pulled into the driveway then reversed. That was a bit weird. Who could that be?"
            thought_data = {
                "trigger_event": selected_event,
                "content": thought_content,
                "mood_impact": "confused", # Using a more descriptive key
                "urgency": "low"
            }
            EventBus.instance().publish(THOUGHT_TRIGGER, thought_data)
            print(f"Published {THOUGHT_TRIGGER} for '{selected_event}': {thought_data}")
        elif selected_event == "mail_delivery":
            thought_content = "Oh, the mail is here! I wonder if there's anything interesting."
            thought_data = {
                "trigger_event": selected_event,
                "content": thought_content,
                "mood_impact": "curious",
                "urgency": "low"
            }
            EventBus.instance().publish(THOUGHT_TRIGGER, thought_data)
            print(f"Published {THOUGHT_TRIGGER} for '{selected_event}': {thought_data}")
        elif selected_event == "stranger_dog_barks":
            thought_content = "Was that a dog barking nearby? Hope it's okay."
            thought_data = {
                "trigger_event": selected_event,
                "content": thought_content,
                "mood_impact": "slightly_concerned",
                "urgency": "low"
            }
            EventBus.instance().publish(THOUGHT_TRIGGER, thought_data)
            print(f"Published {THOUGHT_TRIGGER} for '{selected_event}': {thought_data}")
        # Add more event handling logic here for other events in EVENT_POOL
    else:
        print("No random event triggered this time.")

# Example of how this function might be called or tested (optional)
if __name__ == '__main__':
    # This block is for direct testing of the function.

    # Mock handlers to see what events are published
    def mock_world_event_handler(data):
        print(f"[Test WORLD_EVENT Handler] Event received: {data}")

    def mock_thought_trigger_handler(data):
        print(f"[Test THOUGHT_TRIGGER Handler] Event received: {data}")

    bus = EventBus.instance()
    bus.subscribe(WORLD_EVENT, mock_world_event_handler)
    bus.subscribe(THOUGHT_TRIGGER, mock_thought_trigger_handler)

    print("Testing maybe_trigger_random_event...")
    for i in range(10): # Call it multiple times to see varied outcomes
        print(f"\nAttempt {i+1}:")
        maybe_trigger_random_event()

    print("\nRandom event testing finished.")
