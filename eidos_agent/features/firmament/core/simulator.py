# eidos_agent/features/firmament/core/simulator.py
import logging
from datetime import datetime, timezone
import asyncio # Added

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

# --- Imports for Subconscious NPC Reference Processing ---
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
        async def improvise_npc(self, nh, stc, sc): # Dummy is now async
            logger.warning("DUMMY NPCImproviser.improvise_npc (async) called.");
            return {"id":"dummy_async_npc","name":nh or "DummyAsyncNPC", "role":"dummy_role"} if nh else None
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
PLUGIN_SYSTEM_AVAILABLE_SIM = False # Renamed to avoid conflict with NPC_SYSTEM_AVAILABLE in dummy context
try:
    from .. import get_plugin_manager
    from ..plugins.manager import PluginManager
    PLUGIN_SYSTEM_AVAILABLE_SIM = True
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

    if callable(maybe_trigger_random_event):
        maybe_trigger_random_event()
    else: # pragma: no cover
        logger.warning("Simulator: maybe_trigger_random_event is not callable.")

    if NPC_SYSTEM_AVAILABLE:
        try:
            # TODO: NPCImproviser should ideally be a shared instance.
            npc_improviser = NPCImproviser()
            registry = NPCRegistry.instance()
            recent_thoughts_data = get_recent_subconscious_thoughts(limit=5)
            if recent_thoughts_data:
                thought_contents = [t['content'] for t in recent_thoughts_data if isinstance(t, dict) and 'content' in t]
                original_thought_payloads = {t['content']: t for t in recent_thoughts_data if isinstance(t, dict) and 'content' in t}
                known_npc_profiles = registry.get_all_npcs()
                new_references = extract_character_references(thought_contents, known_npc_profiles)

                for name_hint, thought_context_text in new_references:
                    logger.info(f"Simulator: New NPC reference detected: '{name_hint}' from thought: '{thought_context_text[:70]}...'")

                    location = _current_active_block_data.get('location_hint', _current_active_block_data.get('name', 'unknown_location')) if _current_active_block_data else 'an unspecified place'
                    activity = _current_active_block_data.get('name', 'an unknown activity') if _current_active_block_data else 'an unknown activity'
                    pathos_mood = "neutral (placeholder)"

                    scene_context = {
                        "location_description": location,
                        "pathos_mood_state": pathos_mood,
                        "current_activity_name": activity,
                        "time_of_day": current_time_iso_for_tick,
                    }

                    # --- MODIFIED CALL to async improvise_npc ---
                    # TODO: This asyncio.run() call is a temporary bridge for calling an async method
                    # from the synchronous run_simulation_tick(). If Firmament's core loop becomes async,
                    # this should be 'await npc_improviser.improvise_npc(...)'.
                    # If many such async calls are needed per tick, consider a task gathering pattern
                    # or running the entire tick in an async context managed by the application's main loop.
                    # logger.info(f"Simulator: Preparing to call async improvise_npc for '{name_hint}' via asyncio.run.")
                    improvised_profile = asyncio.run(npc_improviser.improvise_npc(name_hint, thought_context_text, scene_context))
                    # logger.info(f"Simulator: Call to async improvise_npc completed for '{name_hint}'. Profile: {'Found' if improvised_profile else 'None'}")

                    if improvised_profile and isinstance(improvised_profile, dict) and improvised_profile.get("name") and improvised_profile.get("id"):
                        success = registry.register_npc(npc_data=improvised_profile)
                        if success:
                            logger.info(f"Simulator: Registered improvised NPC: '{improvised_profile['name']}' (ID: {improvised_profile['id']})")

                            memory_payload = {
                                "type": "npc_improvised",
                                "content": f"A new persona, '{improvised_profile['name']}' (ID: {improvised_profile['id']}), was improvised by Firmament based on a thought about '{name_hint}'. Role: {improvised_profile.get('role', 'N/A')}.",
                                "metadata": { "npc_id": improvised_profile["id"], "npc_name": improvised_profile["name"],
                                              "triggering_thought_snippet": thought_context_text[:150], "timestamp": current_time_iso_for_tick }} # Simplified metadata for prompt
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
    if PLUGIN_SYSTEM_AVAILABLE_SIM and callable(get_plugin_manager): # Use renamed flag
        plugin_mgr = get_plugin_manager()
        if plugin_mgr and hasattr(plugin_mgr, 'run_plugin_updates') and callable(plugin_mgr.run_plugin_updates):
            # logger.debug(f"Simulator: Running plugin updates at {current_time_iso_for_tick}.")
            plugin_mgr.run_plugin_updates(current_time_iso_for_tick, _current_active_block_data)
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
    def main_test_event_handler_for_sim_async(event_type, data): # Renamed for clarity
        _test_events_captured_sim_main.append({"type": event_type, "data": data})
        print(f"    [SIM_MAIN_CAPTURE] Event: {event_type}, Main Data: {str(data.get('content', data.get('block', {}).get('name', data.get('improvised_npc_profile',{}).get('name', '...'))))[:60]}")


    if hasattr(EventBus, '_instance'): EventBus._instance = None
    test_bus_sim_main_async = EventBus.instance() # Renamed for clarity
    if hasattr(test_bus_sim_main_async, '_subscribers'): test_bus_sim_main_async._subscribers = defaultdict(list)

    event_types_for_main_testing_async = [
        SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED, WORLD_EVENT,
        THOUGHT_TRIGGER, EVENT_MEMORY_WRITE, NEW_NPC_IMPROVISED
    ]
    # Add IMPULSE and NPC_DIALOGUE only if they are actually defined (not dummies)
    if 'IMPULSE' in globals() and (not isinstance(globals()['IMPULSE'], str) or "dummy" not in str(globals().get('IMPULSE',''))):
        event_types_for_main_testing_async.append(globals()['IMPULSE'])
    if 'NPC_DIALOGUE' in globals() and (not isinstance(globals()['NPC_DIALOGUE'], str) or "dummy" not in str(globals().get('NPC_DIALOGUE',''))):
        event_types_for_main_testing_async.append(globals()['NPC_DIALOGUE'])

    for et_name_obj_main_async in event_types_for_main_testing_async:
        actual_et_name_str_main_async = str(getattr(et_name_obj_main_async, 'value', et_name_obj_main_async))
        def create_main_test_handler_async(et_cap_name_str_arg): return lambda d: main_test_event_handler_for_sim_async(et_cap_name_str_arg, d)
        test_bus_sim_main_async.subscribe(actual_et_name_str_main_async, create_main_test_handler_async(actual_et_name_str_main_async))

    mock_thoughts_main_async = [{'content': "Think of Cassandra for asyncio.run test.", 'timestamp': 'ts_main_test_async', 'source': 'main_test_subconscious_async'}]
    mock_profile_main_async = {"id": "cass_async_run_test", "name": "Cassandra AsyncRun Test Improv", "role": "Async Test Role"}

    class MockNPCRegistryMainSimAsync: # Renamed for clarity
        def __init__(self): self.npcs_registered_in_test = {}; print("MockNPCRegistryMainSimAsync Initialized")
        def get_all_npcs(self): return list(self.npcs_registered_in_test.values())
        def register_npc(self, npc_data):
            npc_id = npc_data.get('id')
            if not npc_id: logger.error("MockNPCRegistryMainSimAsync: register_npc called with no ID in npc_data."); return False
            # print(f"MockNPCRegistryMainSimAsync: Registering NPC ID {npc_id}")
            self.npcs_registered_in_test[npc_id] = npc_data; return True
    mock_registry_main_inst_sim_async = MockNPCRegistryMainSimAsync()

    print("\n--- Testing Simulator Tick with ASYNC NPC Improvisation (Patching asyncio.run) ---")
    _current_active_block_data = None

    # Patch asyncio.run as it's used in simulator.py
    with patch('eidos_agent.features.firmament.core.simulator.asyncio.run', return_value=mock_profile_main_async) as mock_asyncio_run_call, \
         patch('eidos_agent.features.firmament.core.simulator.NPC_SYSTEM_AVAILABLE', True), \
         patch('eidos_agent.features.firmament.core.simulator.get_recent_subconscious_thoughts', return_value=mock_thoughts_main_async) as m_get_thoughts, \
         patch('eidos_agent.features.firmament.core.simulator.extract_character_references', return_value=[("Cassandra", mock_thoughts_main_async[0]['content'])]) as m_extract_refs, \
         patch('eidos_agent.features.firmament.core.simulator.NPCRegistry.instance', return_value=mock_registry_main_inst_sim_async) as m_registry_factory, \
         patch('eidos_agent.features.firmament.core.simulator.maybe_trigger_random_event') as m_random_events, \
         patch('eidos_agent.features.firmament.core.simulator.get_plugin_manager', return_value=None) as m_get_plugin_manager: # Keep plugins quiet for this test

        _set_current_block_for_testing({"id": "test_sim_block_async_call", "name": "Activity Async Call", "type": "testing"})
        run_simulation_tick()

    mock_asyncio_run_call.assert_called_once()
    coroutine_arg_to_run = mock_asyncio_run_call.call_args[0][0]
    assert hasattr(coroutine_arg_to_run, '__await__'), "asyncio.run was not called with an awaitable."

    # Check if the coroutine is from an NPCImproviser instance and is the 'improvise_npc' method
    # This is a bit more involved if NPCImproviser itself is a dummy due to other import errors.
    if NPC_SYSTEM_AVAILABLE and hasattr(coroutine_arg_to_run, '__self__') and isinstance(coroutine_arg_to_run.__self__, NPCImproviser):
        assert coroutine_arg_to_run.__name__ == 'improvise_npc', "asyncio.run not called with NPCImproviser.improvise_npc method."
    elif not NPC_SYSTEM_AVAILABLE and hasattr(coroutine_arg_to_run, '__self__') and "DummyNPCImproviser" in str(type(coroutine_arg_to_run.__self__)):
         assert coroutine_arg_to_run.__name__ == 'improvise_npc', "asyncio.run not called with DUMMY NPCImproviser.improvise_npc method."


    assert len(mock_registry_main_inst_sim_async.npcs_registered_in_test) == 1, \
        f"Expected 1 NPC registered, got {len(mock_registry_main_inst_sim_async.npcs_registered_in_test)}"
    if mock_registry_main_inst_sim_async.npcs_registered_in_test: # Check if list is not empty
        registered_npc_ids = list(mock_registry_main_inst_sim_async.npcs_registered_in_test.keys())
        assert mock_profile_main_async["id"] in registered_npc_ids, \
            f"Registered NPC ID mismatch. Expected '{mock_profile_main_async['id']}', found in {registered_npc_ids}"

    new_npc_events_main_async = [e for e in _test_events_captured_sim_main if e['type'] == str(NEW_NPC_IMPROVISED)]
    assert len(new_npc_events_main_async) == 1, f"Expected 1 NEW_NPC_IMPROVISED event in __main__, got {len(new_npc_events_main_async)}."
    if new_npc_events_main_async:
        assert new_npc_events_main_async[0]['data']['improvised_npc_profile']['id'] == mock_profile_main_async["id"]

    print("Asyncio.run call for NPC improvisation in simulator tick verified in __main__.")
    _current_active_block_data = None
    print("\n--- Simulator main test finished ---")
