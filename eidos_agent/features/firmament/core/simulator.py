# eidos_agent/features/firmament/core/simulator.py
import logging
from datetime import datetime, timezone
import asyncio

from .event_bus import EventBus
from .event_types import SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED, WORLD_EVENT, THOUGHT_TRIGGER, NEW_NPC_IMPROVISED

# --- Integration Imports ---
try:
    from ..integrations.chronos_adapter import get_current_block
    from ..integrations.chronos_adapter import _set_current_block_for_testing # For __main__
except ImportError: # pragma: no cover
    print("CRITICAL: Could not import from chronos_adapter. Simulator will use dummy for get_current_block.")
    def get_current_block(): return {"id": "dummy_error_block", "name": "Error Block", "type": "error"} #type:ignore
    _set_current_block_for_testing = lambda d=None: None #type:ignore

try:
    from ..core.event_handlers.random_events import maybe_trigger_random_event
except ImportError: # pragma: no cover
    print("CRITICAL: Could not import from random_events. Simulator will not trigger random events.")
    maybe_trigger_random_event = lambda: None #type:ignore

# --- NPC System Imports ---
NPC_SYSTEM_AVAILABLE = False
try:
    from ..integrations.subconscious_hook import get_recent_subconscious_thoughts
    from ..npcs.subconscious_reference_parser import extract_character_references
    from ..npcs.npc_improviser import NPCImproviser
    from ..npcs.npc_registry import NPCRegistry
    NPC_SYSTEM_AVAILABLE = True
except ImportError as e: # pragma: no cover
    print(f"CRITICAL: Could not import NPC system components for simulator: {e}. NPC improvisation will be disabled.")
    get_recent_subconscious_thoughts = lambda limit=5: [] #type:ignore
    extract_character_references = lambda thoughts, known_profiles: [] #type:ignore
    class NPCImproviser: #type:ignore
        def __init__(self, r=None): logger.warning("Using DUMMY NPCImproviser due to import error.")
        async def improvise_npc(self, nh, stc, sc): logger.warning("DUMMY NPCImproviser.improvise_npc called."); return None
    class NPCRegistry: #type:ignore
        _instance=None
        @classmethod
        def instance(cls):
            logger.warning("Using DUMMY NPCRegistry due to import error.")
            if not cls._instance: cls._instance = cls()
            return cls._instance
        def get_all_npcs(self): return []
        def register_npc(self, npc_data): logger.warning("DUMMY NPCRegistry.register_npc called."); return False

# --- Plugin Manager Import ---
PLUGIN_SYSTEM_AVAILABLE = False
try:
    # Assuming simulator.py is in firmament/core/
    # and __init__.py for firmament is one level up, providing get_plugin_manager
    from .. import get_plugin_manager
    from ..plugins.manager import PluginManager # For type hint if needed, and for dummy
    PLUGIN_SYSTEM_AVAILABLE = True
except ImportError as e: # pragma: no cover
    print(f"CRITICAL: Could not import get_plugin_manager or PluginManager: {e}. Plugin updates will not run.")
    get_plugin_manager = lambda: None #type:ignore
    class PluginManager: #type:ignore
        def __init__(self, eb, nr, fc, pdo=None, psco=None): pass
        def run_plugin_updates(self, current_time_iso, active_block_data) -> None:
            logger.warning("DUMMY PluginManager.run_plugin_updates called.")


logger = logging.getLogger(__name__)
_current_active_block_data: dict | None = None
EVENT_MEMORY_WRITE = "memory.write"

def run_simulation_tick():
    global _current_active_block_data
    current_time_iso_for_tick = datetime.now(timezone.utc).isoformat()
    # logger.debug(f"Simulator: Tick start {current_time_iso_for_tick}. Prev block: {_current_active_block_data.get('id') if _current_active_block_data else 'None'}")

    # --- Schedule Block Transition Logic ---
    new_block_data = get_current_block()
    if not isinstance(new_block_data, dict) or not new_block_data.get("id"):
        if _current_active_block_data:
            EventBus.instance().publish(SCHEDULE_BLOCK_ENDED, {"block": _current_active_block_data, "reason": "new_block_data_invalid_or_none"})
            _current_active_block_data = None
    else:
        new_block_id = new_block_data.get("id")
        previous_block_id = _current_active_block_data.get("id") if _current_active_block_data else None
        if new_block_id != previous_block_id:
            if _current_active_block_data:
                EventBus.instance().publish(SCHEDULE_BLOCK_ENDED, {"block": _current_active_block_data, "reason": "block_changed"})
            EventBus.instance().publish(SCHEDULE_BLOCK_STARTED, {"block": new_block_data})
            _current_active_block_data = new_block_data

    # --- Random World Event Triggering ---
    if callable(maybe_trigger_random_event):
        maybe_trigger_random_event()
    else: # pragma: no cover
        logger.warning("Simulator: maybe_trigger_random_event is not callable.")

    # --- Subconscious NPC Reference Processing ---
    if NPC_SYSTEM_AVAILABLE:
        try:
            npc_improviser = NPCImproviser()
            registry = NPCRegistry.instance()
            recent_thoughts_data = get_recent_subconscious_thoughts(limit=5)
            if recent_thoughts_data:
                thought_contents = [t['content'] for t in recent_thoughts_data if isinstance(t, dict) and 'content' in t]
                original_thought_payloads = {t['content']: t for t in recent_thoughts_data if isinstance(t, dict) and 'content' in t}
                known_npc_profiles = registry.get_all_npcs()
                new_references = extract_character_references(thought_contents, known_npc_profiles)

                for name_hint, thought_context_text in new_references:
                    # logger.info(f"Simulator: New NPC ref: '{name_hint}' from thought: '{thought_context_text[:70]}...'") # Can be verbose
                    # Use current_time_iso_for_tick for consistency within this tick
                    location = _current_active_block_data.get('location_hint', _current_active_block_data.get('name', 'unknown_location')) if _current_active_block_data else 'an unspecified place'
                    activity = _current_active_block_data.get('name', 'an unknown activity') if _current_active_block_data else 'an unknown activity'
                    pathos_mood = "neutral (placeholder)"
                    scene_context = {"location_description": location, "pathos_mood_state": pathos_mood, "current_activity_name": activity, "time_of_day": current_time_iso_for_tick}

                    # logger.info(f"Simulator: Preparing to call async improvise_npc for '{name_hint}'.")
                    improvised_profile = asyncio.run(npc_improviser.improvise_npc(name_hint, thought_context_text, scene_context))
                    # logger.info(f"Simulator: Call to async improvise_npc for '{name_hint}' completed. Profile: {'Found' if improvised_profile else 'None'}")

                    if improvised_profile and isinstance(improvised_profile, dict) and improvised_profile.get("name") and improvised_profile.get("id"):
                        success = registry.register_npc(npc_data=improvised_profile)
                        if success:
                            # logger.info(f"Simulator: Registered improvised NPC: '{improvised_profile['name']}' (ID: {improvised_profile['id']})")
                            memory_payload = {
                                "type": "npc_improvised",
                                "content": f"A new persona, '{improvised_profile['name']}' (ID: {improvised_profile['id']}), was improvised by Firmament based on a thought about '{name_hint}'. Role: {improvised_profile.get('role', 'N/A')}.",
                                "metadata": { "npc_id": improvised_profile["id"], "npc_name": improvised_profile["name"],
                                              "triggering_thought_snippet": thought_context_text[:150], "timestamp": current_time_iso_for_tick }}
                            EventBus.instance().publish(EVENT_MEMORY_WRITE, memory_payload)
                            original_thought = original_thought_payloads.get(thought_context_text, {})
                            new_npc_event_payload = {"improvised_npc_profile": improvised_profile, "triggering_thought_content": thought_context_text,
                                                     "original_subconscious_thought_payload": original_thought, "scene_context_at_improvisation": scene_context }
                            EventBus.instance().publish(NEW_NPC_IMPROVISED, new_npc_event_payload)
                            # logger.info(f"Simulator: Published NEW_NPC_IMPROVISED for '{improvised_profile['name']}'.")
        except Exception as e: # pragma: no cover
            logger.error(f"Simulator: Error during subconscious NPC reference processing: {e}", exc_info=True)
    # else: logger.debug("NPC System not available...")


    # --- Plugin Updates ---
    if PLUGIN_SYSTEM_AVAILABLE and callable(get_plugin_manager):
        plugin_mgr = get_plugin_manager()
        if plugin_mgr and hasattr(plugin_mgr, 'run_plugin_updates') and callable(plugin_mgr.run_plugin_updates):
            # logger.debug(f"Simulator: Running plugin updates at {current_time_iso_for_tick}.")
            plugin_mgr.run_plugin_updates(current_time_iso_for_tick, _current_active_block_data)
        # elif plugin_mgr: logger.warning("Plugin Manager instance found, but run_plugin_updates is not callable.") # pragma: no cover
        # else: logger.debug("Plugin Manager not available (get_plugin_manager returned None). Skipping plugin updates.") # Can be verbose
    # else: # pragma: no cover
        # logger.warning("Plugin system (get_plugin_manager) not available or not callable. Skipping plugin updates.")

    # logger.debug(f"Simulator: Tick finished at {datetime.now(timezone.utc).isoformat()}.")


if __name__ == '__main__': # pragma: no cover
    import unittest.mock
    from collections import defaultdict

    logging.basicConfig(level=logging.INFO)
    sim_logger_main = logging.getLogger('eidos_agent.features.firmament.core.simulator')
    sim_logger_main.setLevel(logging.DEBUG)

    _test_events_captured_sim_main = []
    def main_test_event_handler_for_sim(event_type, data):
        _test_events_captured_sim_main.append({"type": event_type, "data": data})
        # print(f"    [SIM_MAIN_CAPTURE] Event: {event_type}, Main Data: {str(data.get('content', data.get('block', {}).get('name', data.get('improvised_npc_profile',{}).get('name', '...'))))[:60]}")

    if hasattr(EventBus, '_instance'): EventBus._instance = None
    test_bus_sim_main = EventBus.instance()
    if hasattr(test_bus_sim_main, '_subscribers'): test_bus_sim_main._subscribers = defaultdict(list)

    event_types_for_main_testing = [
        SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED, WORLD_EVENT,
        THOUGHT_TRIGGER, EVENT_MEMORY_WRITE, NEW_NPC_IMPROVISED
    ] # Add more if other direct event subscriptions are needed for a particular test scenario

    for et_name_obj_main in event_types_for_main_testing:
        actual_et_name_str_main = str(getattr(et_name_obj_main, 'value', et_name_obj_main))
        def create_main_test_handler(et_cap_name_str_arg): return lambda d: main_test_event_handler_for_sim(et_cap_name_str_arg, d)
        test_bus_sim_main.subscribe(actual_et_name_str_main, create_main_test_handler(actual_et_name_str_main))


    print("\n--- Testing Simulator Tick with Plugin Update Call (and other systems mocked/controlled) ---")
    _current_active_block_data = None

    # Mock the get_plugin_manager to return a MagicMock instance
    mock_plugin_manager_instance_main = unittest.mock.MagicMock(spec=PluginManager if PLUGIN_SYSTEM_AVAILABLE else object)

    # Patching for a focused test on plugin update call
    # We assume other parts (schedule, random events, NPC system) are functional or also mocked.
    # For this specific test, we want to ensure run_plugin_updates is called.
    with patch('eidos_agent.features.firmament.core.simulator.get_plugin_manager', return_value=mock_plugin_manager_instance_main) as mock_get_pm_call, \
         patch('eidos_agent.features.firmament.core.simulator.NPC_SYSTEM_AVAILABLE', False) as mock_npc_system_off, \
         patch('eidos_agent.features.firmament.core.simulator.maybe_trigger_random_event') as mock_random_event_call, \
         patch('eidos_agent.features.firmament.core.simulator.get_current_block', return_value={"id": "main_test_block_plugins", "name": "Main Test Block for Plugins", "type": "testing"}) as mock_schedule_call :

        run_simulation_tick()

    if PLUGIN_SYSTEM_AVAILABLE and callable(get_plugin_manager):
        mock_get_pm_call.assert_called_once()
        mock_plugin_manager_instance_main.run_plugin_updates.assert_called_once()

        # Check arguments of run_plugin_updates
        args_pm_update, _ = mock_plugin_manager_instance_main.run_plugin_updates.call_args
        assert isinstance(args_pm_update[0], str) # current_time_iso
        assert args_pm_update[1] is not None and args_pm_update[1].get("id") == "main_test_block_plugins" # active_block data
        print("Plugin updates called correctly by simulator tick in __main__ test.")
    else:
        print("Plugin system was not available (due to dummy get_plugin_manager or PLUGIN_SYSTEM_AVAILABLE=False). "
              "Test for run_plugin_updates call was skipped or will show dummy behavior.")


    _current_active_block_data = None # Reset global state
    print("\n--- Simulator __main__ test for plugin integration finished ---")
