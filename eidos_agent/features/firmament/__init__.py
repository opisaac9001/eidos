# eidos_agent/features/firmament/__init__.py
"""
The Firmament module, responsible for world simulation, event processing,
and managing Pathos's interaction with his environment.
This module uses an event-driven architecture.
Initializes and registers core event handlers, services, and plugins upon package import.
"""
import logging
from typing import Optional, Dict, Any, TYPE_CHECKING

# Core Firmament components for registration
try:
    # Assuming this __init__.py is in eidos_agent/features/firmament/
    # Config path: up to eidos_agent, then core.config
    from ...core.config import Config
    from .core.event_bus import EventBus
    from .core.event_types import IMPULSE, THOUGHT_TRIGGER, WORLD_EVENT, NEW_NPC_IMPROVISED
    from .core.http_client_manager import HTTPClientManager # New Import

    from .core.event_handlers.schedule import register_schedule_event_handlers
    from .core.event_handlers.impulse import handle_impulse
    from .core.event_handlers.random_events import register_world_event_logging_handler

    from .integrations.oneiros_adapter import OneirosAdapter, register_oneiros_event_handlers
    from .integrations.subconscious_hook import register_thought_trigger_handler

    from .core.npc_controller import load_npc_profiles, register_npc_event_handlers
    from .npcs.npc_registry import NPCRegistry

    from .core.scene_narrator import register_scene_narrator_handlers

    # Import for Plugin System
    from .plugins.manager import PluginManager
    # Import for the new memory event listener
    from ...services.memory_event_listener import handle_memory_write_event, set_ethos_core_for_memory_event_listener

    if TYPE_CHECKING: # pragma: no cover
        from unittest.mock import MagicMock # For dummy type hints below if needed

except ImportError as e: # pragma: no cover
    logging.basicConfig()
    temp_logger = logging.getLogger(__name__)
    temp_logger.critical(f"CRITICAL IMPORT ERROR in Firmament __init__.py: {e}. Firmament will be non-functional.")
    # Define dummy versions for all imported components
    class Config: get_firmament_module_config = lambda: {}; get_llm_config = lambda r:None #type:ignore
    class EventBus: #type:ignore
        _instance = None
        @classmethod
        def instance(cls):
            if not cls._instance: cls._instance = cls()
            return cls._instance
        def subscribe(self, event_type, handler): pass
        def publish(self, event_type, data): pass
    IMPULSE, THOUGHT_TRIGGER, WORLD_EVENT, NEW_NPC_IMPROVISED = ("d.impulse", "d.thought_trigger", "d.world_event", "d.new_npc_improvised") #type:ignore
    class HTTPClientManager: # New Dummy #type:ignore
        _instance = None
        @classmethod
        def instance(cls):
            if not cls._instance:
                temp_logger.info("Using DUMMY HTTPClientManager.instance()")
                cls._instance = cls()
            return cls._instance
        def get_client(self): return None
        async def startup(self): temp_logger.info("DUMMY HTTPClientManager.startup() called"); pass
        async def shutdown(self): temp_logger.info("DUMMY HTTPClientManager.shutdown() called"); pass

    register_schedule_event_handlers=lambda:None; handle_impulse=lambda d:None; register_world_event_logging_handler=lambda:None #type:ignore
    class OneirosAdapter:pass #type:ignore
    register_oneiros_event_handlers=lambda i:None; register_thought_trigger_handler=lambda:None #type:ignore
    load_npc_profiles=lambda:False; register_npc_event_handlers=lambda:None; #type:ignore

    # Dummy NPCRegistry needs to be a class that can be instantiated for PluginManager dummy
    class NPCRegistry_Dummy: #type:ignore
        def __init__(self): temp_logger.info("Dummy NPCRegistry initialized.")
        def get_all_npcs(self): return []
    NPCRegistry = NPCRegistry_Dummy #type:ignore

    register_scene_narrator_handlers = lambda: None #type:ignore

    # Dummy PluginManager needs to be a class that can be instantiated
    class PluginManager_Dummy: #type:ignore
        def __init__(self,event_bus,npc_registry,firmament_config,plugin_dir_override=None,plugin_specific_configs_override=None):
            self.active_plugins = {}
            temp_logger.info("Dummy PluginManager initialized.")
        def load_plugins(self): temp_logger.info("Dummy PluginManager.load_plugins() called.")
        def run_plugin_updates(self, t, ab=None): pass
        def shutdown_plugins(self): pass
    PluginManager = PluginManager_Dummy #type:ignore


logger = logging.getLogger(__name__)

# Global instances for managers, accessible by other Firmament modules
firmament_plugin_manager: Optional[PluginManager] = None
firmament_http_client_manager: Optional[HTTPClientManager] = None # New Global

def initialize_firmament_systems(): # Renamed for broader scope
    """
    Initializes EventBus, HTTPClientManager, core Firmament event handlers,
    NPC systems, and the PluginManager.
    This function is called automatically when the Firmament package is imported.
    """
    global firmament_plugin_manager, firmament_http_client_manager # Declare global for assignment

    # Helper to check if a function/class is a real imported one or a dummy
    def is_real_component(comp_name_str: str) -> bool:
        comp = globals().get(comp_name_str)
        return callable(comp) and (not hasattr(comp, '__module__') or comp.__module__ != __name__)

    try:
        logger.info("Initializing Firmament systems (EventBus, HTTPClientManager, Handlers, NPC System, Plugins)...")

        # Ensure EventBus is available first
        if not is_real_component('EventBus'): # pragma: no cover
            logger.critical("Firmament: Real EventBus class not available. Cannot proceed with full initialization.")
            return
        event_bus = EventBus.instance()

        # Initialize HTTPClientManager first as other components might need it (even if indirectly via LLMClient)
        if is_real_component('HTTPClientManager'):
            firmament_http_client_manager = HTTPClientManager.instance()
            # Note: firmament_http_client_manager.startup() is async.
            # Cannot easily run it here in a sync __init__.py.
            # The client will initialize lazily on first get_client() if not already.
            # Explicit startup should be handled by an async part of the main application.
            logger.info("Firmament HTTPClientManager singleton instance obtained/created.")
            logger.warning("TODO: firmament_http_client_manager.shutdown() needs to be called by the main "
                           "application during its graceful shutdown sequence to close the HTTP client.")
        else: # pragma: no cover
            logger.error("Firmament: HTTPClientManager not available or is a dummy. LLM-dependent features may fail or use dummies.")

        # --- Register Core Event Handlers ---
        if is_real_component('register_schedule_event_handlers'):
            register_schedule_event_handlers(); logger.info("Registered schedule event handlers.")
        else: logger.error("Firmament: Schedule handler registration function missing!") # pragma: no cover

        if is_real_component('handle_impulse'):
            event_bus.subscribe(IMPULSE, handle_impulse); logger.info("Registered impulse event handler.")
        else: logger.error("Firmament: Impulse handler function missing!") # pragma: no cover

        if is_real_component('register_world_event_logging_handler'):
            register_world_event_logging_handler(); logger.info("Registered world event logging handler.")
        else: logger.error("Firmament: World event logger registration missing!") # pragma: no cover

        if is_real_component('OneirosAdapter') and is_real_component('register_oneiros_event_handlers'):
            default_oneiros_adapter = OneirosAdapter(); register_oneiros_event_handlers(default_oneiros_adapter)
            logger.info("Registered Oneiros event handlers.")
        else: logger.error("Firmament: Oneiros components for registration missing!") # pragma: no cover

        if is_real_component('register_thought_trigger_handler'):
            register_thought_trigger_handler(); logger.info("Registered subconscious thought trigger handler.")
        else: logger.error("Firmament: Thought trigger registration missing!") # pragma: no cover

        if is_real_component('register_scene_narrator_handlers'):
            register_scene_narrator_handlers(); logger.info("Registered scene narrator handlers.")
        else: logger.error("Firmament: Scene narrator registration missing!") # pragma: no cover

        # --- Load NPC System ---
        # logger.info("Attempting to load NPC profiles & register NPC event handlers...") # Less verbose
        if is_real_component('load_npc_profiles') and is_real_component('register_npc_event_handlers'):
            if load_npc_profiles():
                logger.info("NPC profiles loaded successfully.")
                register_npc_event_handlers(); logger.info("Registered NPC event handlers (npc_controller listeners).")
            else: logger.error("NPC profiles failed to load. Some NPC interactions may not work.")
        else: logger.error("Firmament: NPC profile loading/registration functions missing!") # pragma: no cover

        # --- Initialize and Load Plugins ---
        # logger.info("Initializing PluginManager and loading plugins...") # Less verbose
        if is_real_component('PluginManager') and is_real_component('NPCRegistry') and is_real_component('Config'):
            npc_registry_instance = NPCRegistry.instance()
            firmament_module_config = Config.get_firmament_module_config()

            firmament_plugin_manager = PluginManager(
                event_bus=event_bus,
                npc_registry=npc_registry_instance,
                firmament_config=firmament_module_config
            )
            firmament_plugin_manager.load_plugins()
            active_plugin_names = list(firmament_plugin_manager.active_plugins.keys()) if firmament_plugin_manager and firmament_plugin_manager.active_plugins else "None"
            logger.info(f"Plugin loading phase complete. Active plugins: {active_plugin_names}")
        else: # pragma: no cover
            logger.error("Firmament: PluginManager or its core dependencies (NPCRegistry, Config) not available. Plugins not loaded.")

        # Subscribe the generic memory write handler
        if is_real_component('handle_memory_write_event'):
            event_bus.subscribe("memory.write", handle_memory_write_event) # Assuming "memory.write" is the correct event name
            logger.info("Firmament: Subscribed 'memory.write' event to MemoryEventListener.handle_memory_write_event.")
            logger.warning("Firmament IMPORTANT: The MemoryEventListener's EthosCore instance MUST be set "
                           "by the main application after EthosCore is initialized, using "
                           "set_ethos_core_for_memory_event_listener(ethos_core_instance).")
        else: # pragma: no cover
            logger.error("Firmament: MemoryEventListener.handle_memory_write_event not available. Cannot subscribe.")

        logger.info("Firmament systems initialization process completed.")
    except Exception as e: # pragma: no cover
        logger.error(f"CRITICAL ERROR during Firmament systems initialization: {e}", exc_info=True)
        firmament_http_client_manager = None # Ensure managers are None if init failed
        firmament_plugin_manager = None


def get_plugin_manager() -> Optional[PluginManager]:
    """Returns the initialized Firmament PluginManager instance."""
    return firmament_plugin_manager

def get_http_client_manager() -> Optional[HTTPClientManager]: # New Accessor
    """Returns the initialized Firmament HTTPClientManager instance."""
    return firmament_http_client_manager

# --- Automatically initialize when the firmament package is imported ---
if 'EventBus' in globals() and hasattr(EventBus, '__module__') and EventBus.__module__ != __name__:
    initialize_firmament_systems()
else: # pragma: no cover
    logger.warning("Skipping Firmament systems initialization: Critical components (like EventBus) were not imported correctly "
                   "and dummy versions are in place. Check for earlier CRITICAL IMPORT ERROR messages.")

logger.info("eidos_agent.features.firmament package loaded. Initialization attempt status logged above.")

# End of Firmament __init__.py
