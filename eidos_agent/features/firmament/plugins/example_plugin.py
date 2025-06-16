# eidos_agent/features/firmament/plugins/example_plugin.py

# This is an example of a Firmament plugin.
# Plugins can be used to extend Firmament's functionality by:
# - Subscribing to events on the EventBus and reacting to them.
# - Publishing new events to the EventBus.
# - Registering new services or capabilities.

# Assuming EventBus and relevant event types are accessible.
# The exact mechanism for a plugin to get an EventBus instance (e.g., passed in constructor,
# retrieved from a global registry, or via a dedicated plugin manager API) would be
# part of Firmament's plugin architecture.

# For this example, we'll assume EventBus can be imported if this plugin is loaded
# in an environment where 'eidos_agent.features.firmament.core' is in PYTHONPATH.
# Or, more realistically, the event_bus_instance is passed during plugin initialization.

from ..core.event_bus import EventBus # Trying relative import for core modules
from ..core.event_types import WORLD_EVENT, THOUGHT_TRIGGER, MOOD_UPDATED # Example event types

class ExampleFirmamentPlugin:
    PLUGIN_NAME = "ExampleFirmamentPlugin"
    PLUGIN_VERSION = "0.1.0"

    def __init__(self, event_bus_instance: EventBus, config: dict = None):
        """
        Initializes the plugin.

        Args:
            event_bus_instance (EventBus): An instance of the Firmament EventBus.
            config (dict, optional): Plugin-specific configuration. Defaults to None.
        """
        self.event_bus = event_bus_instance
        self.config = config if config else {}
        self.internal_state = {"events_handled": 0, "actions_performed": 0}
        print(f"Plugin '{self.PLUGIN_NAME} v{self.PLUGIN_VERSION}' initialized. Config: {self.config}")

    def setup(self):
        """
        Sets up the plugin by subscribing its handlers to relevant events.
        This method would typically be called by a plugin loader or manager after instantiation.
        """
        print(f"Plugin '{self.PLUGIN_NAME}': Setting up event subscriptions...")
        try:
            # Subscribe to specific world events. The handler will need to filter.
            self.event_bus.subscribe(WORLD_EVENT, self.handle_world_event)
            print(f"  Subscribed 'handle_world_event' to '{WORLD_EVENT}'.")

            # Subscribe to thought triggers
            self.event_bus.subscribe(THOUGHT_TRIGGER, self.handle_thought_trigger)
            print(f"  Subscribed 'handle_thought_trigger' to '{THOUGHT_TRIGGER}'.")

            # Example: Subscribe to mood updates
            self.event_bus.subscribe(MOOD_UPDATED, self.handle_mood_update)
            print(f"  Subscribed 'handle_mood_update' to '{MOOD_UPDATED}'.")

            print(f"Plugin '{self.PLUGIN_NAME}': Setup complete.")
        except Exception as e:
            print(f"Error during {self.PLUGIN_NAME} setup: {e}")


    def handle_world_event(self, data: dict):
        """
        Example handler for WORLD_EVENT. Filters for specific event names.
        """
        self.internal_state["events_handled"] += 1
        # The 'data' for WORLD_EVENT might be like: {"type": "random_world_event", "event_name": "stranger_dog_barks", ...}
        # Or, if published directly by something else, could be simpler: {"event": "stranger_dog_barks"}
        event_name = data.get("event_name", data.get("event")) # Accommodate different payload structures

        if event_name == "stranger_dog_barks":
            print(f"\nPlugin '{self.PLUGIN_NAME}' [WorldEventHandler]: Detected 'stranger_dog_barks' event!")
            print(f"  Event Data: {data}")
            # This plugin could, for example, trigger a new thought or a mood change.
            thought_content = self.config.get("dog_bark_thought", "That dog barking sounds a bit aggressive and close by.")
            new_thought_payload = {
                "content": thought_content,
                "mood_impact": "anxious", # Using 'mood_impact' as per other examples
                "source": self.PLUGIN_NAME
            }
            self.event_bus.publish(THOUGHT_TRIGGER, new_thought_payload)
            print(f"  Published new THOUGHT_TRIGGER: {new_thought_payload}")

        elif event_name == "mail_delivery":
            print(f"\nPlugin '{self.PLUGIN_NAME}' [WorldEventHandler]: Detected 'mail_delivery' event.")
            print(f"  Event Data: {data}")
            # Perhaps this plugin has special logic for mail, e.g., checking if it's a package.
            if data.get("has_package", False):
                 print(f"  Plugin notes: The mail included a package!")


    def handle_thought_trigger(self, data: dict):
        """
        Example handler for a THOUGHT_TRIGGER event.
        """
        self.internal_state["events_handled"] += 1
        thought_content = data.get("content", "Unknown thought content")
        print(f"\nPlugin '{self.PLUGIN_NAME}' [ThoughtTriggerHandler]: Detected THOUGHT_TRIGGER.")
        print(f"  Thought Content: '{thought_content}'")
        print(f"  Full Data: {data}")
        # A plugin might analyze thoughts, log them externally, trigger alerts for certain keywords, etc.
        if "plugin" in thought_content.lower():
            print(f"  Plugin insight: This thought mentions plugins!")


    def handle_mood_update(self, data: dict):
        """
        Example handler for MOOD_UPDATED events.
        """
        self.internal_state["events_handled"] += 1
        print(f"\nPlugin '{self.PLUGIN_NAME}' [MoodUpdateHandler]: Detected MOOD_UPDATED event.")
        print(f"  Mood Data: {data}")
        # Example: if mood 'stress' is high, plugin logs a warning or suggests an action.
        if data.get("stress_level", 0) > 0.7:
            print(f"  Plugin alert: Stress level is high ({data.get('stress_level')})!")


    def custom_plugin_action(self, action_data: dict) -> dict:
        """
        An example of a custom action this plugin might offer, callable perhaps via an API
        or another event.
        """
        self.internal_state["actions_performed"] += 1
        print(f"\nPlugin '{self.PLUGIN_NAME}': Performing 'custom_plugin_action'.")
        print(f"  Action Data: {action_data}")

        # Simulate doing some work based on action_data
        processed_detail = f"Action processed with input '{action_data.get('input_param', 'default')}'."
        result = {"status": "success", "detail": processed_detail, "plugin_name": self.PLUGIN_NAME}

        # This action might also publish an event indicating its completion.
        completion_event_type = f"plugin.{self.PLUGIN_NAME}.action_completed"
        self.event_bus.publish(completion_event_type, result)
        print(f"  Published '{completion_event_type}' with result: {result}")
        return result

    def get_status(self) -> dict:
        """ Returns the internal status of the plugin. """
        return {
            "name": self.PLUGIN_NAME,
            "version": self.PLUGIN_VERSION,
            "state": self.internal_state,
            "config": self.config
        }

# How plugins are discovered, loaded, and initialized would depend on Firmament's
# overall plugin management system. This is a self-contained example of a plugin's structure.

if __name__ == '__main__':
    print("--- Testing ExampleFirmamentPlugin ---")

    # Use the actual EventBus for this integration-style test within the plugin file.
    # This assumes the script is run in an environment where imports resolve.
    # If EventBus has singleton logic, this will use that instance.

    # For a true unit test of the plugin, EventBus should be mocked.
    # But for this __main__ block, let's use the real one to see if imports work.
    try:
        bus = EventBus.instance() # Get the singleton instance
        print("Successfully obtained EventBus instance for testing.")
    except Exception as e:
        print(f"Could not get EventBus instance. Error: {e}")
        print("Cannot run plugin test without EventBus. Exiting.")
        exit()

    # Mock subscribers on the bus to see what the plugin publishes
    _test_plugin_published_events = []
    def mock_listener_for_plugin_thoughts(data):
        print(f"[MockListenerForPluginThoughts] Heard plugin-generated THOUGHT_TRIGGER: {data.get('content')}")
        _test_plugin_published_events.append({"type": THOUGHT_TRIGGER, "data": data})

    def mock_listener_for_plugin_action_completion(data):
        print(f"[MockListenerForPluginAction] Heard plugin action completed: {data.get('detail')}")
        _test_plugin_published_events.append({"type": f"plugin.{ExampleFirmamentPlugin.PLUGIN_NAME}.action_completed", "data": data})

    bus.subscribe(THOUGHT_TRIGGER, mock_listener_for_plugin_thoughts) # Listen for thoughts published by plugin
    bus.subscribe(f"plugin.{ExampleFirmamentPlugin.PLUGIN_NAME}.action_completed", mock_listener_for_plugin_action_completion)

    # Initialize and set up the plugin
    plugin_config = {"dog_bark_thought": "Custom: That dog sounds like it needs a friend!"}
    plugin = ExampleFirmamentPlugin(event_bus_instance=bus, config=plugin_config)
    plugin.setup()

    print("\n1. Simulating a WORLD_EVENT ('stranger_dog_barks') that the plugin handles:")
    world_event_dog = {"event_name": "stranger_dog_barks", "source": "random_event_generator", "intensity": "loud"}
    bus.publish(WORLD_EVENT, world_event_dog)

    print("\n2. Simulating a WORLD_EVENT ('mail_delivery') that the plugin also sees:")
    world_event_mail = {"event_name": "mail_delivery", "source": "random_event_generator", "has_package": True}
    bus.publish(WORLD_EVENT, world_event_mail)

    print("\n3. Simulating a THOUGHT_TRIGGER event (plugin should log this):")
    thought_event = {"content": "This is a thought that the example_plugin might be interested in.", "mood": "analytical"}
    bus.publish(THOUGHT_TRIGGER, thought_event)

    print("\n4. Simulating a MOOD_UPDATED event (plugin should react if stress is high):")
    mood_event_normal = {"happiness": 0.6, "stress_level": 0.3}
    bus.publish(MOOD_UPDATED, mood_event_normal)
    mood_event_stressed = {"happiness": 0.2, "stress_level": 0.8, "cause": "deadline approaching"}
    bus.publish(MOOD_UPDATED, mood_event_stressed)

    print("\n5. Calling the plugin's custom action:")
    action_result = plugin.custom_plugin_action({"input_param": "test_value_123"})
    print(f"   Result of custom_plugin_action: {action_result}")

    print("\n6. Getting plugin status:")
    status = plugin.get_status()
    print(f"   Plugin Status: {status}")

    print("\n--- Summary of Events Published by Plugin (and captured by mock listeners) ---")
    if _test_plugin_published_events:
        for i, evt_info in enumerate(_test_plugin_published_events):
            print(f"  Captured Event {i+1}: Type='{evt_info['type']}', Data='{str(evt_info['data'])[:100]}...'")
    else:
        print("  No events from the plugin were captured by the specific mock listeners.")

    print("\n--- ExampleFirmamentPlugin testing finished ---")
