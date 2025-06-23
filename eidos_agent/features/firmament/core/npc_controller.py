# eidos_agent/features/firmament/core/npc_controller.py

import yaml
import os
import logging
import random
from datetime import datetime, timezone # Added

# Attempt to import EventBus and event types.
try:
    from ..event_bus import EventBus
    from ..event_types import NPC_DIALOGUE, WORLD_EVENT
except ImportError: # pragma: no cover
    print("CRITICAL: NPC_Controller could not import EventBus or core event types. Event handling will fail.")
    class EventBus:  # type: ignore
        _instance = None
        _subscribers: dict = {} # Class attribute for subscribers

        @classmethod
        def instance(cls):
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

        def __init__(self):
            # Ensure instance's subscribers are distinct if class attribute was shared by mistake before
            self._subscribers = {}

        def subscribe(self, event_type, handler):
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if handler not in self._subscribers[event_type]:
                 self._subscribers[event_type].append(handler)
            # print(f"DummyEventBus: Handler {handler.__name__} subscribed to {event_type}")


        def publish(self, event_type, data):
            # print(f"DummyEventBus: Publishing {event_type} with {data}")
            if event_type in self._subscribers:
                for handler in self._subscribers[event_type]:
                    try:
                        handler(data)
                    except Exception as e:
                        print(f"DummyEventBus: Error in handler {handler.__name__} for event {event_type}: {e}")
            # else:
                # print(f"DummyEventBus: No subscribers for event {event_type}")

    NPC_DIALOGUE, WORLD_EVENT = "dummy.npc_dialogue", "dummy.world_event" #type:ignore

logger = logging.getLogger(__name__)
_npc_profiles_data: dict = {}
CONFIG_DIR_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "configs"))

EVENT_MEMORY_WRITE = "memory.write" # Added

def load_npc_profiles(config_file_name: str = "npc_profiles.yaml") -> bool:
    """
    Loads NPC profiles from the specified YAML file into the module-level
    _npc_profiles_data dictionary.
    """
    global _npc_profiles_data
    config_file_path = os.path.join(CONFIG_DIR_PATH, config_file_name)

    # logger.info(f"Attempting to load NPC profiles from: {config_file_path}")
    if not os.path.exists(CONFIG_DIR_PATH): # pragma: no cover
        logger.error(f"Configuration directory does not exist: {CONFIG_DIR_PATH}")
        return False

    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            raw_profiles = yaml.safe_load(f)

        if raw_profiles is None:
            logger.warning(f"NPC profiles file is empty: {config_file_path}")
            _npc_profiles_data.clear()
            return True

        if not isinstance(raw_profiles, dict):
            logger.error(f"NPC profiles YAML content is not a dictionary. File: {config_file_path}")
            return False

        temp_profiles_data = {}
        for npc_id, npc_data in raw_profiles.items():
            if isinstance(npc_data, dict) and npc_data.get("id") == npc_id:
                temp_profiles_data[npc_id] = npc_data
            else:
                logger.warning(f"Skipping profile entry with key '{npc_id}' due to missing/mismatched 'id' in {config_file_path}.")

        _npc_profiles_data.clear()
        _npc_profiles_data.update(temp_profiles_data)
        # logger.info(f"Successfully loaded and validated {len(_npc_profiles_data)} NPC profiles from {config_file_path}.")
        return True

    except FileNotFoundError: # pragma: no cover
        logger.error(f"NPC profiles file not found: {config_file_path}")
    except yaml.YAMLError as e: # pragma: no cover
        logger.error(f"Error parsing NPC profiles YAML file: {config_file_path}. Error: {e}")
    except Exception as e: # pragma: no cover
        logger.error(f"An unexpected error occurred loading NPC profiles from {config_file_path}: {e}", exc_info=True)

    return False

def spawn_npc_interaction(triggering_event_data: dict):
    """
    Generates NPC interactions based on triggering world events and loaded NPC profiles.
    If an NPC is triggered by the event, it publishes an NPC_DIALOGUE event with a selected
    dialogue line and an EVENT_MEMORY_WRITE event to log the NPC's presence.
    """
    event_name = triggering_event_data.get("event_name")
    if not event_name:
        logger.warning(f"NPC Controller: spawn_npc_interaction called with no 'event_name' in data: {triggering_event_data}")
        return

    # logger.debug(f"NPC Controller: Processing event_name '{event_name}' for NPC interaction.")

    for npc_id, npc_profile in _npc_profiles_data.items():
        presence_triggers = npc_profile.get("presence_trigger_events", [])
        if not isinstance(presence_triggers, list): # Ensure presence_triggers is a list
            # logger.warning(f"NPC {npc_id} has malformed presence_trigger_events (not a list). Skipping.")
            continue

        if event_name in presence_triggers:
            npc_name = npc_profile.get("name", npc_id)
            # logger.info(f"NPC Controller: Event '{event_name}' triggered NPC '{npc_name}' (ID: {npc_id}).")

            dialogue_lines_map = npc_profile.get("dialogue_lines", {})
            if not isinstance(dialogue_lines_map, dict): # Ensure dialogue_lines_map is a dict
                # logger.warning(f"NPC {npc_name} has malformed dialogue_lines (not a dictionary). Using default response.")
                dialogue_lines_map = {}

            chosen_dialogue_line = ""

            # Try event-specific dialogue first
            event_dialogue_key = f"event_{event_name}"
            event_specific_lines = dialogue_lines_map.get(event_dialogue_key, [])
            if event_specific_lines and isinstance(event_specific_lines, list) and event_specific_lines:
                chosen_dialogue_line = random.choice(event_specific_lines)
            # Fallback to general greeting
            elif dialogue_lines_map.get("greeting_general") and isinstance(dialogue_lines_map["greeting_general"], list) and dialogue_lines_map["greeting_general"]:
                chosen_dialogue_line = random.choice(dialogue_lines_map["greeting_general"])
            else:
                # Default line if no suitable dialogue is found
                chosen_dialogue_line = f"{npc_name} acknowledges the {event_name} event."

            # Publish NPC_DIALOGUE event
            dialogue_payload = {
                "npc_id": npc_id, # Crucial for identifying the NPC
                "npc_name": npc_name,
                "line": chosen_dialogue_line,
                "triggering_event_name": event_name, # Context about what brought the NPC
                "mood": npc_profile.get("default_mood", "neutral") # Optionally include NPC's current mood
            }
            EventBus.instance().publish(NPC_DIALOGUE, dialogue_payload)
            # logger.debug(f"NPC Controller: Published NPC_DIALOGUE: {dialogue_payload}")

            # Publish memory.write event for NPC presence
            presence_memory_content = f"{npc_name} (ID: {npc_id}) is present due to the '{event_name}' event."
            presence_memory_payload = {
                "type": "npc_presence", # Specific type for this memory
                "content": presence_memory_content,
                "metadata": {
                    "npc_id": npc_id,
                    "npc_name": npc_name,
                    "triggering_event_name": event_name,
                    "dialogue_spoken": chosen_dialogue_line, # Include what was said
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }
            EventBus.instance().publish(EVENT_MEMORY_WRITE, presence_memory_payload)
            # logger.debug(f"NPC Controller: Published npc_presence memory: {presence_memory_payload}")

            # For now, handle only the first matching NPC for a given event to keep it simple.
            # Future enhancements could allow multiple NPCs to react or have a priority system.
            break
    # else:
        # logger.debug(f"NPC Controller: No NPC profile found a trigger for event_name '{event_name}'.")


def register_npc_event_listeners():
    """
    Subscribes NPC interaction handlers to relevant world events.
    """
    if "EventBus" in globals() and callable(EventBus.instance):
        try:
            EventBus.instance().subscribe(WORLD_EVENT, spawn_npc_interaction)
            # logger.info("NPC Controller: Subscribed spawn_npc_interaction to WORLD_EVENT.")
        except Exception as e: # pragma: no cover
             logger.error(f"Error subscribing NPC_Controller to EventBus: {e}")
    # else: # pragma: no cover
        # logger.error("NPC Controller: EventBus not available for subscribing event listeners.")


if __name__ == '__main__': # pragma: no cover
    # from collections import defaultdict # No longer needed if dummy EventBus is more robust

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    print("--- Testing NPC Controller with Profile Loading & Spawn Interaction ---")

    # Ensure dummy EventBus is used for __main__ if imports failed
    # This is tricky because the class definition is global.
    # If the real EventBus was imported, this __main__ might use it.
    # For robust __main__ testing when imports fail, the dummy needs to be effective.
    # The current dummy structure should work if the ImportError was hit.

    if not load_npc_profiles():
        print("FATAL: Could not load NPC profiles for test. Aborting __main__ test for spawn_npc_interaction.")
    else:
        _test_events_npc_main = []
        def capture_npc_events(event_type, data):
            print(f"    [Capture] Event: {event_type}, Relevant Data: {str(data.get('npc_name', data.get('content', data)))[:80]}...")
            _test_events_npc_main.append({"type": event_type, "data": data})

        # Get an instance of EventBus (could be real or dummy)
        bus = EventBus.instance()

        # For __main__ testing, explicitly clear subscribers on the dummy if it's the dummy,
        # to ensure a clean state for this test run.
        if hasattr(bus, '_subscribers') and isinstance(bus._subscribers, dict): # Check if it's our dummy
            print("    Note: Clearing subscribers on the dummy EventBus for __main__ test.")
            bus._subscribers.clear()

        bus.subscribe(NPC_DIALOGUE, lambda data: capture_npc_events(NPC_DIALOGUE, data))
        bus.subscribe(EVENT_MEMORY_WRITE, lambda data: capture_npc_events(EVENT_MEMORY_WRITE, data))

        # This will subscribe spawn_npc_interaction to WORLD_EVENT on the bus instance
        register_npc_event_listeners()

        print("\n--- Test 1: Event that should trigger Mailman Bob ('mail_delivery') ---")
        _test_events_npc_main.clear()
        mail_event = {"event_name": "mail_delivery", "source": "test_harness_npc", "detail": "Package for Pathos"}
        bus.publish(WORLD_EVENT, mail_event)

        npc_dialogues = [e for e in _test_events_npc_main if e["type"] == NPC_DIALOGUE]
        npc_presence_logs = [e for e in _test_events_npc_main if e["type"] == EVENT_MEMORY_WRITE and e["data"].get("type") == "npc_presence"]

        assert len(npc_dialogues) == 1, f"Expected 1 NPC_DIALOGUE for mail_delivery, got {len(npc_dialogues)}"
        if npc_dialogues:
            assert npc_dialogues[0]["data"]["npc_id"] == "mailman_bob", "NPC ID should be mailman_bob"
            assert "Mailman Bob" in npc_dialogues[0]["data"]["npc_name"], "NPC name mismatch"
            print(f"  Mailman Bob dialogue: '{npc_dialogues[0]['data']['line']}'")

        assert len(npc_presence_logs) == 1, f"Expected 1 npc_presence log for mail_delivery, got {len(npc_presence_logs)}"
        if npc_presence_logs:
            assert npc_presence_logs[0]["data"]["metadata"]["npc_id"] == "mailman_bob"
            assert "Mailman Bob (ID: mailman_bob) is present due to 'mail_delivery' event." in npc_presence_logs[0]["data"]["content"]
            print(f"  Mailman Bob presence logged: '{npc_presence_logs[0]['data']['content']}'")


        print("\n--- Test 2: Event that should trigger Neighbor Alice ('neighbor_starts_lawnmower') ---")
        _test_events_npc_main.clear()
        lawnmower_event = {"event_name": "neighbor_starts_lawnmower", "source": "test_harness_npc", "sound_level": "loud"}
        bus.publish(WORLD_EVENT, lawnmower_event)

        npc_dialogues = [e for e in _test_events_npc_main if e["type"] == NPC_DIALOGUE]
        npc_presence_logs = [e for e in _test_events_npc_main if e["type"] == EVENT_MEMORY_WRITE and e["data"].get("type") == "npc_presence"]
        assert len(npc_dialogues) == 1, f"Expected 1 NPC_DIALOGUE for lawnmower, got {len(npc_dialogues)}"
        if npc_dialogues: assert npc_dialogues[0]["data"]["npc_id"] == "neighbor_alice"
        assert len(npc_presence_logs) == 1, f"Expected 1 npc_presence log for lawnmower, got {len(npc_presence_logs)}"
        if npc_presence_logs: assert npc_presence_logs[0]["data"]["metadata"]["npc_id"] == "neighbor_alice"
        print(f"  Neighbor Alice dialogue: '{npc_dialogues[0]['data']['line'] if npc_dialogues else 'N/A'}'")


        print("\n--- Test 3: Event that should NOT trigger any specific NPC dialogue ('birds_chirping') ---")
        _test_events_npc_main.clear()
        birds_event = {"event_name": "birds_chirping", "source": "test_harness_npc", "type_of_bird": "robin"}
        bus.publish(WORLD_EVENT, birds_event)

        npc_dialogues = [e for e in _test_events_npc_main if e["type"] == NPC_DIALOGUE]
        npc_presence_logs = [e for e in _test_events_npc_main if e["type"] == EVENT_MEMORY_WRITE and e["data"].get("type") == "npc_presence"]
        assert len(npc_dialogues) == 0, f"Expected 0 NPC_DIALOGUE for birds_chirping, got {len(npc_dialogues)}"
        assert len(npc_presence_logs) == 0, f"Expected 0 npc_presence logs for birds_chirping, got {len(npc_presence_logs)}"
        print("  Correctly no NPC dialogue or presence log for 'birds_chirping'.")

        print("\nNPC controller spawn interaction testing finished.")
