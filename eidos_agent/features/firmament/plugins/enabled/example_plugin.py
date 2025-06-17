# eidos_agent/features/firmament/plugins/enabled/example_plugin.py
# (Note: This file is now in the 'enabled' subdirectory)

from typing import Dict, Optional, Any, TYPE_CHECKING # Added TYPE_CHECKING
from collections import defaultdict # For __main__ mock event bus

# Adjust import for FirmamentPluginBase based on new location
# plugins/enabled/example_plugin.py -> plugins/plugin_base.py (one level up)
try:
    from ..plugin_base import FirmamentPluginBase
    # Assuming EventBus and NPCRegistry types might be needed for hinting in setup
    # Path from enabled -> plugins -> firmament -> core
    # Path from enabled -> plugins -> firmament -> npcs
    if TYPE_CHECKING: # pragma: no cover
        from ....core.event_bus import EventBus
        from ....npcs.npc_registry import NPCRegistry
    from ....core.event_types import WORLD_EVENT, THOUGHT_TRIGGER, MOOD_UPDATED
except ImportError: # pragma: no cover
    # This block is primarily for allowing the file to be parsed if imports fail,
    # e.g., when running this file directly without the full package structure in PYTHONPATH.
    # In a real plugin scenario, these imports should resolve correctly.
    print("ERROR in example_plugin.py: Could not resolve imports for FirmamentPluginBase or core types. Using dummies.")
    from unittest.mock import MagicMock # For dummy logger if logging isn't set up
    class FirmamentPluginBase: #type:ignore
        def __init__(self, plugin_name: str, firmament_config: Optional[Dict[str, Any]]=None, plugin_specific_config: Optional[Dict[str, Any]]=None):
            self.plugin_name=plugin_name
            self.firmament_config = firmament_config or {}
            self.plugin_specific_config = plugin_specific_config or {}
            self.logger=MagicMock(spec=logging.Logger) # Use MagicMock for dummy logger
            self.is_setup_complete=False
            self.logger.info(f"Dummy FirmamentPluginBase '{plugin_name}' initialized.")
        def setup(self, event_bus: Any, npc_registry: Any) -> bool: self.is_setup_complete=True; self.logger.info("Dummy setup called."); return True
        def update_on_tick(self, current_time_iso: str, active_block: Optional[Dict[str, Any]]=None): self.logger.debug("Dummy update_on_tick.")
        def get_status(self) -> Dict[str, Any]: return {"name": self.plugin_name, "is_setup": self.is_setup_complete, "status": "dummy"}
        def shutdown(self): self.logger.info("Dummy shutdown called.")
    EventBus=Any; NPCRegistry=Any; WORLD_EVENT="dummy.world_event"; THOUGHT_TRIGGER="dummy.thought_trigger"; MOOD_UPDATED="dummy.mood_updated" #type:ignore
    import logging # Ensure logging is imported for dummy logger to have a spec


class ExampleFirmamentPlugin(FirmamentPluginBase):
    """
    An example plugin demonstrating the FirmamentPluginBase structure.
    This plugin logs some events and has a simple tick update.
    It can be configured via plugin_specific_config.
    """
    PLUGIN_NAME = "ExamplePlugin001"
    PLUGIN_VERSION = "0.2.0"

    def __init__(self, plugin_name: str, firmament_config: Optional[Dict[str, Any]] = None, plugin_specific_config: Optional[Dict[str, Any]] = None):
        """
        Initializes the ExampleFirmamentPlugin. Args are passed by the PluginManager.
        """
        # plugin_name passed to super() will be self.PLUGIN_NAME if PluginManager uses that,
        # or the class name if PLUGIN_NAME is not defined. The manager should handle this.
        # For direct instantiation (like in __main__), we pass it explicitly.
        super().__init__(plugin_name, firmament_config, plugin_specific_config)

        # These will be properly typed if TYPE_CHECKING block works with actual imports
        self.event_bus: Optional['EventBus'] = None
        self.npc_registry: Optional['NPCRegistry'] = None

        self.events_handled_count = 0
        self.tick_updates_received = 0

        # self.logger is already initialized by the base class.
        self.logger.info(f"Plugin '{self.plugin_name} v{self.PLUGIN_VERSION}' __init__ called.")
        self.logger.debug(f"  Firmament Config available: {bool(self.firmament_config)}")
        self.logger.debug(f"  Plugin Specific Config: {self.plugin_specific_config}")

    def setup(self, event_bus: 'EventBus', npc_registry: 'NPCRegistry') -> bool:
        """
        Sets up the plugin by storing core components and subscribing to events.
        """
        self.logger.info(f"Plugin '{self.plugin_name}' performing setup...")
        self.event_bus = event_bus
        self.npc_registry = npc_registry

        if not self.event_bus: # pragma: no cover
            self.logger.error("EventBus instance not provided to setup. Cannot subscribe to events.")
            self.is_setup_complete = False
            return False

        try:
            self.event_bus.subscribe(WORLD_EVENT, self.handle_world_event)
            self.logger.info(f"Subscribed 'handle_world_event' to '{WORLD_EVENT}'.")

            self.event_bus.subscribe(THOUGHT_TRIGGER, self.handle_thought_trigger_example)
            self.logger.info(f"Subscribed 'handle_thought_trigger_example' to '{THOUGHT_TRIGGER}'.")

            if self.plugin_specific_config.get("subscribe_to_mood_updates", False):
                self.event_bus.subscribe(MOOD_UPDATED, self.handle_mood_update_example)
                self.logger.info(f"Subscribed 'handle_mood_update_example' to '{MOOD_UPDATED}' (config driven).")

            self.is_setup_complete = True
            self.logger.info(f"Plugin '{self.plugin_name}' setup completed successfully.")
            return True
        except Exception as e: # pragma: no cover
            self.logger.error(f"Error during '{self.plugin_name}' setup: {e}", exc_info=True)
            self.is_setup_complete = False
            return False

    def handle_world_event(self, data: Dict[str, Any]):
        self.events_handled_count += 1
        event_name = data.get("event_name", data.get("event", "unknown_world_event"))
        self.logger.info(f"Plugin '{self.plugin_name}' [WorldEventHandler]: Detected '{event_name}'. Data snippet: {str(data)[:100]}...")

        target_event = self.plugin_specific_config.get("target_world_event_for_reaction", "phone_buzzes_on_table")
        if event_name == target_event:
            self.logger.info(f"Plugin '{self.plugin_name}' reacting specifically to its configured target event: '{event_name}'!")
            if self.event_bus:
                self.event_bus.publish(THOUGHT_TRIGGER, {
                    "content": f"The {self.plugin_name} observed the '{event_name}' event and had a specific, configured thought about it.",
                    "mood": self.plugin_specific_config.get("reaction_mood", "analytical"),
                    "source": self.plugin_name,
                    "urgency": self.plugin_specific_config.get("reaction_urgency", "low")
                })

    def handle_thought_trigger_example(self, data: Dict[str, Any]):
        self.events_handled_count += 1
        self.logger.info(f"Plugin '{self.plugin_name}' [ThoughtTriggerHandler]: Observed thought: '{data.get('content', '')[:60]}...'")

    def handle_mood_update_example(self, data: Dict[str, Any]):
        self.events_handled_count += 1
        self.logger.info(f"Plugin '{self.plugin_name}' [MoodUpdateHandler]: Pathos's mood updated: {data}")


    def update_on_tick(self, current_time_iso: str, active_block: Optional[Dict[str, Any]] = None) -> None:
        super().update_on_tick(current_time_iso, active_block)
        self.tick_updates_received += 1
        # Log less frequently to avoid spamming logs, e.g., every 10th tick or on significant condition
        if self.tick_updates_received % self.plugin_specific_config.get("log_tick_frequency", 10) == 0:
            self.logger.info(f"Plugin '{self.plugin_name}' received tick update #{self.tick_updates_received} at {current_time_iso}. "
                             f"Active block: {active_block.get('name') if active_block else 'None'}")

    def get_status(self) -> Dict[str, Any]:
        base_status = super().get_status()
        base_status.update({
            "version": self.PLUGIN_VERSION,
            "events_handled_count": self.events_handled_count,
            "tick_updates_received": self.tick_updates_received,
            "target_world_event_for_reaction": self.plugin_specific_config.get("target_world_event_for_reaction"),
            "custom_message": f"{self.plugin_name} is operational and monitoring."
        })
        return base_status

    def shutdown(self) -> None:
        super().shutdown()
        self.logger.info(f"Plugin '{self.plugin_name}' performing specific shutdown actions (e.g., saving plugin state if any).")


if __name__ == '__main__': # pragma: no cover
    import logging # Ensure logging is imported for __main__
    from collections import defaultdict # For mock event bus

    # Setup for standalone testing of this plugin file
    logging.basicConfig(level=logging.DEBUG) # See all logs from plugin and base
    main_logger = logging.getLogger(__name__ + ".__main__")

    # Mock Firmament components for this standalone test
    class MockEvtBusForPluginMain:
        def __init__(self): self.subscriptions = defaultdict(list); self.published_events = []
        def subscribe(self, event_type, handler):
            self.subscriptions[event_type].append(handler)
            main_logger.info(f"MockEvtBus: Handler '{getattr(handler, '__name__', str(handler))}' subscribed to '{event_type}'")
        def publish(self, event_type, data):
            main_logger.info(f"MockEvtBus: Publishing '{event_type}' with data: {data}")
            self.published_events.append({"type": event_type, "data": data})
            # Also dispatch to subscribers for interactive testing if needed
            for handler_func in self.subscriptions.get(event_type, []):
                handler_func(data) # type: ignore

    class MockNPCRegForPluginMain:
        def list_known_npc_ids(self): return ["npc_main_mock_001"]

    test_bus_main = MockEvtBusForPluginMain()
    test_registry_main = MockNPCRegForPluginMain()

    # Test with specific config for the plugin
    plugin_configuration = {
        "subscribe_to_mood_updates": True,
        "target_world_event_for_reaction": "power_flickers_briefly",
        "reaction_mood": "surprised_by_plugin",
        "log_tick_frequency": 3 # Log tick updates more frequently for test
    }
    firmament_main_config = {"global_sim_setting": "test_value_firmament", "version": "beta"}

    print("\n--- Initializing ExampleFirmamentPlugin for __main__ test ---")
    # Use the plugin's own PLUGIN_NAME if defined, or the one passed in.
    # PluginManager would typically pass plugin_class.PLUGIN_NAME or class name.
    example_plugin = ExampleFirmamentPlugin(
        plugin_name=ExampleFirmamentPlugin.PLUGIN_NAME, # Use defined PLUGIN_NAME
        firmament_config=firmament_main_config,
        plugin_specific_config=plugin_configuration
    )

    print(f"\n--- Setting up {example_plugin.plugin_name} ---")
    setup_success_main = example_plugin.setup(event_bus=test_bus_main, npc_registry=test_registry_main)
    assert setup_success_main, "Plugin setup failed in __main__ test"

    print("\n--- Simulating Events for the Plugin ---")
    test_bus_main.publish(WORLD_EVENT, {"event_name": "power_flickers_briefly", "detail": "lights went out for a moment"})
    test_bus_main.publish(WORLD_EVENT, {"event_name": "other_random_event", "detail": "something else occurred"})
    test_bus_main.publish(THOUGHT_TRIGGER, {"content": "A test thought specifically for the plugin to see."})
    test_bus_main.publish(MOOD_UPDATED, {"current_mood_name": "happy", "intensity": 0.85, "dominant_emotion": "joy"})

    print("\n--- Simulating Ticks for the Plugin ---")
    for i in range(5): # Simulate 5 ticks
        example_plugin.update_on_tick(f"2023-10-28T12:0{i}:00Z", {"id": f"block_{i}", "name": f"Activity Block {i}"})

    print("\n--- Getting Plugin Status ---")
    status_report_main = example_plugin.get_status()
    print(f"Plugin Status Report: {status_report_main}")
    assert status_report_main["events_handled_count"] == 4, "Incorrect events_handled_count in status."
    assert status_report_main["tick_updates_received"] == 5, "Incorrect tick_updates_received in status."
    assert status_report_main["target_world_event_for_reaction"] == "power_flickers_briefly"

    # Check if the reaction thought was published
    reaction_thought_published = any(
        evt["type"] == THOUGHT_TRIGGER and
        "power_flickers_briefly" in evt["data"].get("content","") and
        evt["data"].get("source") == ExampleFirmamentPlugin.PLUGIN_NAME
        for evt in test_bus_main.published_events
    )
    assert reaction_thought_published, "Plugin did not publish its reaction THOUGHT_TRIGGER."

    print("\n--- Shutting Down Plugin ---")
    example_plugin.shutdown()

    print(f"\n--- ExampleFirmamentPlugin __main__ test completed successfully. Total events published on mock bus: {len(test_bus_main.published_events)} ---")
