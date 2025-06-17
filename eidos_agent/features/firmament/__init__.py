# eidos_agent/features/firmament/__init__.py
"""
The Firmament module, responsible for world simulation, event processing,
and managing Pathos's interaction with his environment.
This module uses an event-driven architecture.
Initializes and registers core event handlers upon package import.
"""
import logging

# Core Firmament components for registration
# It's important that these imports are successful for the module to initialize correctly.
try:
    from .core.event_bus import EventBus
    # Import event types that are directly used for subscriptions in this file (IMPULSE)
    # or are good to have for context (THOUGHT_TRIGGER, WORLD_EVENT).
    from .core.event_types import IMPULSE, THOUGHT_TRIGGER, WORLD_EVENT

    from .core.event_handlers.schedule import register_schedule_event_handlers
    from .core.event_handlers.impulse import handle_impulse
    # Import for the world event logger (which listens to WORLD_EVENT)
    from .core.event_handlers.random_events import register_world_event_logging_handler

    from .integrations.oneiros_adapter import OneirosAdapter, register_oneiros_event_handlers
    from .integrations.subconscious_hook import register_thought_trigger_handler # Handles THOUGHT_TRIGGER

    # Example for NPC interaction handling registration, if it follows a similar pattern:
    # from .core.npc_controller import register_npc_event_listeners

except ImportError as e: # pragma: no cover
    logging.basicConfig()
    temp_logger = logging.getLogger(__name__)
    temp_logger.critical(f"CRITICAL IMPORT ERROR in Firmament __init__.py: {e}. "
                         "Firmament event handlers will NOT be registered. "
                         "Ensure all submodules and dependencies are correct.")
    # Define dummy versions for critical components so the file can parse,
    # but the module will be non-functional.
    class EventBus: instance = lambda: EventBus(); subscribe = lambda s,e,h: None # type: ignore
    IMPULSE, THOUGHT_TRIGGER, WORLD_EVENT = "dummy.impulse", "dummy.thought_trigger", "dummy.world_event" # type: ignore
    register_schedule_event_handlers = lambda: None # type: ignore
    handle_impulse = lambda d: None # type: ignore
    register_world_event_logging_handler = lambda: None # type: ignore
    class OneirosAdapter: pass # type: ignore
    register_oneiros_event_handlers = lambda i: None # type: ignore
    register_thought_trigger_handler = lambda: None # type: ignore
    # register_npc_event_listeners = lambda: None # type: ignore


logger = logging.getLogger(__name__)

def initialize_firmament_event_handlers():
    """
    Initializes the EventBus and registers all core Firmament event handlers.
    This function is called automatically when the Firmament package is imported.
    """
    try:
        logger.info("Initializing Firmament event handlers...")
        event_bus = EventBus.instance() # Ensures EventBus is created

        # Register schedule event handlers (handles SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED)
        register_schedule_event_handlers()
        logger.info("Registered Firmament schedule event handlers.")

        # Register impulse handler (handles IMPULSE events)
        event_bus.subscribe(IMPULSE, handle_impulse)
        logger.info("Registered Firmament impulse event handler for IMPULSE events.")

        # Register world event logging handler (handles WORLD_EVENT for logging purposes)
        # This function itself subscribes handle_world_event_logging to WORLD_EVENT
        if 'register_world_event_logging_handler' in globals() and callable(globals()['register_world_event_logging_handler']):
            register_world_event_logging_handler()
            logger.info("Registered Firmament world event logging handler.")
        else: # Should not be reached if imports are correct
            logger.error("Firmament: register_world_event_logging_handler function not found/callable!")


        # Register Oneiros event handlers (handles "oneiros.start_dream_sequence")
        default_oneiros_adapter_instance = OneirosAdapter()
        register_oneiros_event_handlers(default_oneiros_adapter_instance)
        logger.info("Registered Firmament Oneiros event handlers.")

        # Register subconscious thought trigger handler (handles THOUGHT_TRIGGER events)
        # This function subscribes subconscious_hook.handle_thought_trigger to THOUGHT_TRIGGER
        register_thought_trigger_handler()
        logger.info("Registered Firmament subconscious thought trigger handler.")

        # Example: Register NPC event listeners if such a registration function exists
        # if 'register_npc_event_listeners' in globals() and callable(globals()['register_npc_event_listeners']):
        #     register_npc_event_listeners()
        #     logger.info("Registered Firmament NPC event listeners.")

        logger.info("Firmament core event handlers initialization complete.")

    except Exception as e: # pragma: no cover
        logger.error(f"Error during Firmament event handler initialization: {e}", exc_info=True)


# --- Automatically initialize handlers when the firmament package is imported ---
# This check ensures initialization only proceeds if critical imports (like EventBus) were successful.
if 'EventBus' in globals() and hasattr(EventBus, '__module__') and EventBus.__module__ != __name__:
    initialize_firmament_event_handlers()
else: # pragma: no cover
    logger.warning("Skipping Firmament event handler initialization due to prior critical import errors or dummy EventBus.")

logger.info("eidos_agent.features.firmament package loaded. Core event handler registration attempted.")

# For direct use by other parts of the application:
# from eidos_agent.features.firmament.core.simulator import run_simulation_tick
# from eidos_agent.features.firmament.core.event_bus import EventBus
# from eidos_agent.features.firmament.core.event_types import *
```
