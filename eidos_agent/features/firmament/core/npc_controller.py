# eidos_agent/features/firmament/core/npc_controller.py

# This module will manage NPC (Non-Player Character) generation,
# their behaviors, dialogues, and interactions within the simulation.

# Adjust import paths as necessary for the Eidos project structure
from ..event_bus import EventBus
from ..event_types import NPC_DIALOGUE, WORLD_EVENT # Ensure NPC_DIALOGUE is "npc.say" as per event_types.py

# Placeholder for NPC profiles or more complex NPC management
NPC_PROFILES = {
    "Mailman": {
        "dialogue_generic": ["Looks like a nice day.", "Here's the mail."],
        "dialogue_package": "Hey there! Got a package for you today.",
        "dialogue_no_package": "Just the usual letters today."
    },
    "Neighbor": {
        "dialogue_generic": ["Morning!", "How are you doing?", "Nice weather we're having."],
    }
}

def spawn_npc_interaction(triggering_event_data: dict):
    """
    Generates NPC interactions based on triggering events (e.g., world events).
    Publishes NPC dialogue events.
    """
    # event_data here is the data from the event that triggered this function,
    # e.g., a WORLD_EVENT.
    print(f"NPC Controller: spawn_npc_interaction triggered by event data: {triggering_event_data}")

    # The design doc implies that this function is called with data that has an "event" key,
    # which describes the type of world event, like "mail_delivery".
    # Let's assume triggering_event_data might be something like:
    # {"type": "random_world_event", "event_name": "mail_delivery", ...}
    # Or directly {"event": "mail_delivery"} if published that way.

    event_name_from_trigger = triggering_event_data.get("event_name") # if coming from our random_events.py
    if not event_name_from_trigger: # Fallback if the key is "event" directly
        event_name_from_trigger = triggering_event_data.get("event")

    npc_name = None
    dialogue_line = None

    if event_name_from_trigger == "mail_delivery":
        npc_name = "Mailman"
        # Example: Decide dialogue based on more detailed event data if available
        if triggering_event_data.get("has_package", True): # Assume package by default for this event
            dialogue_line = NPC_PROFILES.get(npc_name, {}).get("dialogue_package", "Hello! Mail's here.")
        else:
            dialogue_line = NPC_PROFILES.get(npc_name, {}).get("dialogue_no_package", "Hello! Mail's here.")

        print(f"NPC Controller: Mailman interaction triggered for '{event_name_from_trigger}'.")

    # Add more NPC interaction triggers and logic here
    # Example: A neighbor passes by due to a different world event
    # elif event_name_from_trigger == "neighbor_sighting":
    #     npc_name = "Neighbor"
    #     dialogue_line = random.choice(NPC_PROFILES.get(npc_name, {}).get("dialogue_generic", ["Hi."]))
    #     print(f"NPC Controller: Neighbor interaction triggered for '{event_name_from_trigger}'.")

    else:
        print(f"NPC Controller: No specific NPC interaction defined for event '{event_name_from_trigger}'.")
        return # No interaction to publish

    if npc_name and dialogue_line:
        # Publishing to NPC_DIALOGUE event type (which should be "npc.say")
        EventBus.instance().publish(NPC_DIALOGUE, {
            "npc_name": npc_name, # Changed key to be more descriptive
            "line": dialogue_line,
            "source_trigger_event": event_name_from_trigger # Optional: trace where this interaction originated
        })
        print(f"NPC Controller: Published {NPC_DIALOGUE} - {npc_name} says: '{dialogue_line}'")


# Example of how one might subscribe this to an event (for testing or integration)
# This setup function would typically be called during application initialization.
def register_npc_event_listeners():
    """
    Subscribes NPC interaction handlers to relevant world events.
    """
    # This assumes that WORLD_EVENT's data payload will contain an "event_name"
    # or "event" key that spawn_npc_interaction can use.
    EventBus.instance().subscribe(WORLD_EVENT, spawn_npc_interaction)
    print("NPC Controller: Subscribed spawn_npc_interaction to WORLD_EVENT.")

if __name__ == '__main__':
    # Basic test setup for npc_controller.py
    # This requires EventBus and NPC_DIALOGUE, WORLD_EVENT from event_types to be accessible.

    # Mock handler for NPC_DIALOGUE to see if it's published
    def mock_npc_dialogue_handler(data):
        print(f"[Test NPC_DIALOGUE Handler] Event received: {data}")

    bus = EventBus.instance()
    bus.subscribe(NPC_DIALOGUE, mock_npc_dialogue_handler)

    # Register the NPC listener (subscribes spawn_npc_interaction to WORLD_EVENT)
    register_npc_event_listeners()

    print("\nTesting NPC mail delivery interaction (via WORLD_EVENT)...")
    # Simulate a world event that should trigger the mailman
    mail_event_data = {"type": "random_world_event", "event_name": "mail_delivery", "has_package": True, "source": "test_harness"}
    bus.publish(WORLD_EVENT, mail_event_data)

    print("\nTesting NPC mail delivery interaction (no package)...")
    mail_event_data_no_package = {"type": "random_world_event", "event_name": "mail_delivery", "has_package": False, "source": "test_harness"}
    bus.publish(WORLD_EVENT, mail_event_data_no_package)

    print("\nTesting NPC interaction with an unhandled world event type...")
    # Simulate a world event that currently has no specific NPC interaction defined
    unhandled_event_data = {"type": "random_world_event", "event_name": "birds_chirping", "source": "test_harness"}
    bus.publish(WORLD_EVENT, unhandled_event_data)

    print("\nNPC controller testing finished.")
