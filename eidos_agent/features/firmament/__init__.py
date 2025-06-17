# eidos_agent/features/firmament/__init__.py
"""
The Firmament module, responsible for world simulation, event processing,
and managing Pathos's interaction with his environment.
This module uses an event-driven architecture.
Initializes and registers core event handlers and plugins upon package import.
"""
import logging
from typing import Optional, Dict, Any # Added Optional, Dict, Any

# Core Firmament components for registration
try:
    # Assuming this __init__.py is in eidos_agent/features/firmament/
    # Config path: up to eidos_agent, then core.config
    from ...core.config import Config
    from .core.event_bus import EventBus
    from .core.event_types import IMPULSE, THOUGHT_TRIGGER, WORLD_EVENT, NEW_NPC_IMPROVISED

    from .core.event_handlers.schedule import register_schedule_event_handlers
    from .core.event_handlers.impulse import handle_impulse
    from .core.event_handlers.random_events import register_world_event_logging_handler

    from .integrations.oneiros_adapter import OneirosAdapter, register_oneiros_event_handlers
    from .integrations.subconscious_hook import register_thought_trigger_handler

    from .core.npc_controller import load_npc_profiles, register_npc_event_handlers
    from .npcs.npc_registry import NPCRegistry # For PluginManager

    from .core.scene_narrator import register_scene_narrator_handlers

    # Import for Plugin System
    from .plugins.manager import PluginManager

except ImportError as e: # pragma: no cover
    logging.basicConfig()
    temp_logger = logging.getLogger(__name__)
    temp_logger.critical(f"CRITICAL IMPORT ERROR in Firmament __init__.py: {e}. Firmament will be non-functional.")
    # Define dummy versions for all imported components
    class Config: #type:ignore
        @staticmethod
        def get_firmament_module_config(): return {"firmament_llm_role": "FIRMAMENT_PRIMARY_DUMMY"}
    class EventBus: #type:ignore
        _instance = None
        @classmethod
        def instance(cls):
            if not cls._instance: cls._instance = cls()
            return cls._instance
        def subscribe(self, event_type, handler): pass
        def publish(self, event_type, data): pass
    IMPULSE, THOUGHT_TRIGGER, WORLD_EVENT, NEW_NPC_IMPROVISED = ("dummy.impulse", "dummy.thought_trigger", "dummy.world_event", "dummy.new_npc_improvised") #type:ignore
    register_schedule_event_handlers = lambda: None #type:ignore
    handle_impulse = lambda data: None #type:ignore
    register_world_event_logging_handler = lambda: None #type:ignore
    class OneirosAdapter: pass #type:ignore
    register_oneiros_event_handlers = lambda instance: None #type:ignore
    register_thought_trigger_handler = lambda: None #type:ignore
    load_npc_profiles = lambda: False #type:ignore
    register_npc_event_handlers = lambda: None #type:ignore
    class NPCRegistry: #type:ignore
        _instance = None
        @classmethod
        def instance(cls):
            if not cls._instance: cls._instance = cls()
            return cls._instance
        def get_all_npcs(self): return [] # Required by simulator for NPC improvisation logic
    register_scene_narrator_handlers = lambda: None #type:ignore
    class PluginManager: #type:ignore
        def __init__(self, event_bus, npc_registry, firmament_config, plugin_dir_override=None, plugin_specific_configs_override=None):
            self.active_plugins = {}
            temp_logger.info("Dummy PluginManager initialized.")
        def load_plugins(self): temp_logger.info("Dummy PluginManager.load_plugins() called.")
        def run_plugin_updates(self, t, ab=None): pass
        def shutdown_plugins(self): pass


logger = logging.getLogger(__name__)

# Global instance for the Plugin Manager, accessible by other Firmament modules if needed (e.g., simulator for tick updates)
firmament_plugin_manager: Optional[PluginManager] = None

def initialize_firmament_event_handlers_and_plugins(): # Renamed for clarity
    """
    Initializes EventBus, core Firmament event handlers, NPC systems, and the PluginManager.
    This function is called automatically when the Firmament package is imported.
    """
    global firmament_plugin_manager # Declare global for assignment

    # Helper to check if a function is a real imported one or a dummy
    def is_real_callable(func_name_str: str) -> bool:
        func = globals().get(func_name_str)
        return callable(func) and (not hasattr(func, '__module__') or func.__module__ != __name__)

    try:
        logger.info("Initializing Firmament: EventBus, core handlers, NPC system, and plugins...")

        # Ensure EventBus is available first
        if not is_real_callable('EventBus'): # pragma: no cover
            logger.critical("Firmament: Real EventBus class not available. Cannot proceed with initialization.")
            return
        event_bus = EventBus.instance()

        # --- Register Core Event Handlers ---
        if is_real_callable('register_schedule_event_handlers'):
            register_schedule_event_handlers(); logger.info("Registered schedule event handlers.")
        else: logger.error("Firmament: Schedule handler registration function missing!") # pragma: no cover

        if is_real_callable('handle_impulse'):
            event_bus.subscribe(IMPULSE, handle_impulse); logger.info("Registered impulse event handler.")
        else: logger.error("Firmament: Impulse handler function missing!") # pragma: no cover

        if is_real_callable('register_world_event_logging_handler'):
            register_world_event_logging_handler(); logger.info("Registered world event logging handler.")
        else: logger.error("Firmament: World event logger registration missing!") # pragma: no cover

        if is_real_callable('OneirosAdapter') and is_real_callable('register_oneiros_event_handlers'):
            default_oneiros_adapter = OneirosAdapter(); register_oneiros_event_handlers(default_oneiros_adapter)
            logger.info("Registered Oneiros event handlers.")
        else: logger.error("Firmament: Oneiros components for registration missing!") # pragma: no cover

        if is_real_callable('register_thought_trigger_handler'):
            register_thought_trigger_handler(); logger.info("Registered subconscious thought trigger handler.")
        else: logger.error("Firmament: Thought trigger registration missing!") # pragma: no cover

        if is_real_callable('register_scene_narrator_handlers'):
            register_scene_narrator_handlers(); logger.info("Registered scene narrator handlers.")
        else: logger.error("Firmament: Scene narrator registration missing!") # pragma: no cover


        # --- Load NPC System ---
        logger.info("Attempting to load NPC profiles & register NPC event handlers...")
        if is_real_callable('load_npc_profiles') and is_real_callable('register_npc_event_handlers'):
            if load_npc_profiles():
                logger.info("NPC profiles loaded successfully.")
                register_npc_event_handlers(); logger.info("Registered NPC event handlers (npc_controller listeners).")
            else: logger.error("NPC profiles failed to load. Some NPC interactions may not work.")
        else: logger.error("Firmament: NPC profile loading/registration functions missing!") # pragma: no cover

        # --- Initialize and Load Plugins ---
        logger.info("Initializing PluginManager and loading plugins...")
        if is_real_callable('PluginManager') and is_real_callable('NPCRegistry') and is_real_callable('Config'):

            npc_registry_instance = NPCRegistry.instance() # Get (or create) the singleton
            firmament_module_config = Config.get_firmament_module_config() # Get main Firmament config

            firmament_plugin_manager = PluginManager(
                event_bus=event_bus,
                npc_registry=npc_registry_instance,
                firmament_config=firmament_module_config
                # plugin_dir_override and plugin_specific_configs_override will use defaults in PluginManager
            )
            firmament_plugin_manager.load_plugins() # Discovers and calls setup() on plugins

            active_plugin_names = list(firmament_plugin_manager.active_plugins.keys()) if firmament_plugin_manager.active_plugins else "None"
            logger.info(f"Plugin loading phase complete. Active plugins: {active_plugin_names}")
        else: # pragma: no cover
            logger.error("Firmament: PluginManager or its core dependencies (NPCRegistry, Config) not available. Plugins not loaded.")

        logger.info("Firmament event handlers and plugins initialization completed.")
    except Exception as e: # pragma: no cover
        logger.error(f"CRITICAL ERROR during Firmament full initialization: {e}", exc_info=True)
        # Ensure plugin manager is None if init failed badly
        firmament_plugin_manager = None


def get_plugin_manager() -> Optional[PluginManager]:
    """
    Returns the initialized Firmament PluginManager instance.
    Returns None if the PluginManager has not been initialized (e.g., due to import errors).
    """
    return firmament_plugin_manager

# --- Automatically initialize when the firmament package is imported ---
# Check if EventBus is the real one (not a dummy from ImportError block)
if 'EventBus' in globals() and hasattr(EventBus, '__module__') and EventBus.__module__ != __name__:
    initialize_firmament_event_handlers_and_plugins() # Call the renamed function
else: # pragma: no cover
    logger.warning("Skipping Firmament full initialization: Critical components (like EventBus) were not imported correctly "
                   "and dummy versions are in place. Check for earlier CRITICAL IMPORT ERROR messages.")

logger.info("eidos_agent.features.firmament package loaded. Initialization attempt status logged above.")

# For direct use by other parts of the application:
# from eidos_agent.features.firmament.core.simulator import run_simulation_tick
# from eidos_agent.features.firmament.core.event_bus import EventBus
# from eidos_agent.features.firmament.core.event_types import *
# from eidos_agent.features.firmament import get_plugin_manager
```
