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
    from .core.event_types import IMPULSE, THOUGHT_TRIGGER # THOUGHT_TRIGGER for subconscious_hook

    from .core.event_handlers.schedule import register_schedule_event_handlers
    from .core.event_handlers.impulse import handle_impulse
    # For NPC interactions, if npc_controller also has a registration function:
    # from .core.npc_controller import register_npc_event_listeners # Example

    from .integrations.oneiros_adapter import OneirosAdapter, register_oneiros_event_handlers
    from .integrations.subconscious_hook import register_thought_trigger_handler # Handles THOUGHT_TRIGGER

except ImportError as e: # pragma: no cover
    # This error means Firmament cannot initialize properly.
    # Log a critical error and potentially re-raise or exit if this is fatal for the application.
    logging.basicConfig() # Ensure basicConfig is called if logger below fails
    temp_logger = logging.getLogger(__name__)
    temp_logger.critical(f"CRITICAL IMPORT ERROR in Firmament __init__.py: {e}. "
                         "Firmament event handlers will NOT be registered. "
                         "Ensure all submodules and dependencies are correct.")
    # Depending on application strictness, could raise a RuntimeError here:
    # raise RuntimeError(f"Firmament failed to initialize due to ImportError: {e}") from e
    # For now, we'll allow the rest of the file to parse to avoid breaking `ls` or other tools
    # but the module will be in a non-functional state for event handling.
    # Define dummy versions so the rest of the file can be parsed by tools if imports fail.
    class EventBus: instance = lambda: EventBus(); subscribe = lambda s,e,h: None # type: ignore
    IMPULSE, THOUGHT_TRIGGER = "dummy.impulse", "dummy.thought_trigger" # type: ignore
    register_schedule_event_handlers = lambda: None # type: ignore
    handle_impulse = lambda d: None # type: ignore
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

        # Get EventBus instance (it's a singleton, this ensures it's created if not already)
        event_bus = EventBus.instance()

        # Register schedule event handlers (handles SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED)
        register_schedule_event_handlers()
        logger.info("Registered Firmament schedule event handlers.")

        # Register impulse handler (handles IMPULSE)
        event_bus.subscribe(IMPULSE, handle_impulse)
        logger.info("Registered Firmament impulse event handler for IMPULSE events.")

        # Register Oneiros event handlers (handles "oneiros.start_dream_sequence")
        # OneirosAdapter might have its own config loaded from elsewhere in a full app.
        # For this auto-registration, we use a default instance.
        default_oneiros_adapter_instance = OneirosAdapter() # Assuming default config is okay for now
        register_oneiros_event_handlers(default_oneiros_adapter_instance)
        logger.info("Registered Firmament Oneiros event handlers.")

        # Register subconscious thought trigger handler (handles THOUGHT_TRIGGER)
        # This function itself subscribes subconscious_hook.handle_thought_trigger to THOUGHT_TRIGGER
        register_thought_trigger_handler()
        logger.info("Registered Firmament subconscious thought trigger handler.")

        # Example: Register NPC event listeners if defined
        # if 'register_npc_event_listeners' in globals() and callable(globals()['register_npc_event_listeners']):
        #     register_npc_event_listeners()
        #     logger.info("Registered Firmament NPC event listeners.")

        logger.info("Firmament core event handlers initialization complete.")

    except Exception as e: # pragma: no cover
        logger.error(f"Error during Firmament event handler initialization: {e}", exc_info=True)
        # Depending on policy, this could be a critical failure.

# --- Automatically initialize handlers when the firmament package is imported ---
# This makes the module self-configuring to a basic extent for core functionalities.
# Ensure this is only called if the critical imports at the top succeeded.
if 'EventBus' in globals() and EventBus.__module__ != __name__: # Check if real EventBus was imported
    initialize_firmament_event_handlers()
else: # pragma: no cover
    logger.warning("Skipping Firmament event handler initialization due to prior critical import errors.")


logger.info("eidos_agent.features.firmament package loaded. Core event handler registration attempted.")

# Key components for direct use by other parts of the application can still be imported from submodules, e.g.:
# from eidos_agent.features.firmament.core.simulator import run_simulation_tick
# from eidos_agent.features.firmament.core.event_bus import EventBus # To publish events from outside Firmament
# from eidos_agent.features.firmament.integrations.subconscious_hook import handle_thought_trigger (for direct calls if needed)
# from eidos_agent.features.firmament.core.event_types import * # To reference specific event types
```
