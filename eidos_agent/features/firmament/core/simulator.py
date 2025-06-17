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
            logger.warning("DUMMY NPCImproviser.improvise_npc called.");
            # Return a dict that looks like a profile for dummy testing
            return {"id": "dummy_improv_id", "name": nh or "Dummy Improv NPC", "role": "dummy_role"}
    class NPCRegistry: #type:ignore
        _instance=None
        @classmethod
        def instance(cls):
            logger.warning("Using DUMMY NPCRegistry due to import error.")
            if not cls._instance: cls._instance = cls()
            return cls._instance
        def get_all_npcs(self): return []
        def register_npc(self, npc_data): logger.warning("DUMMY NPCRegistry.register_npc called."); return False


logger = logging.getLogger(__name__)
_current_active_block_data: dict | None = None
EVENT_MEMORY_WRITE = "memory.write"

def run_simulation_tick():
    global _current_active_block_data

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
        logger.warning("Simulator: maybe_trigger_random_event is not callable (likely import error).")

    if NPC_SYSTEM_AVAILABLE:
        # logger.debug("Simulator: Checking for subconscious NPC references...")
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

                    current_time_iso = datetime.now(timezone.utc).isoformat()
                    location = _current_active_block_data.get('location_hint', _current_active_block_data.get('name', 'unknown_location')) if _current_active_block_data else 'an unspecified place'
                    activity = _current_active_block_data.get('name', 'an unknown activity') if _current_active_block_data else 'an unknown activity'
                    pathos_mood = "neutral (placeholder)"

                    scene_context = {
                        "location_description": location,
                        "pathos_mood_state": pathos_mood,
                        "current_activity_name": activity,
                        "time_of_day": current_time_iso,
                    }

                    # --- MODIFIED CALL to async improvise_npc ---
                    # TODO: This asyncio.run() call is a temporary bridge for calling an async method
                    # from the synchronous run_simulation_tick(). If Firmament's core loop becomes async,
                    # this should be 'await npc_improviser.improvise_npc(...)'.
                    # If many such async calls are needed per tick, consider a task gathering pattern
                    # or running the entire tick in an async context managed by the application's main loop.
                    # logger.info(f"Simulator: Preparing to call async improvise_npc for '{name_hint}'.")
                    improvised_profile = asyncio.run(npc_improviser.improvise_npc(name_hint, thought_context_text, scene_context))
                    # logger.info(f"Simulator: Call to async improvise_npc completed for '{name_hint}'. Profile: {'Found' if improvised_profile else 'None'}")

                    if improvised_profile and isinstance(improvised_profile, dict) and improvised_profile.get("name") and improvised_profile.get("id"):
                        success = registry.register_npc(npc_data=improvised_profile)
                        if success:
                            logger.info(f"Simulator: Registered improvised NPC: '{improvised_profile['name']}' (ID: {improvised_profile['id']})")

                            memory_payload = {
                                "type": "npc_improvised",
                                "content": f"A new persona, '{improvised_profile['name']}' (ID: {improvised_profile['id']}), was improvised by Firmament based on a thought about '{name_hint}'. Role: {improvised_profile.get('role', 'N/A')}.",
                                "metadata": {
                                    "npc_id": improvised_profile["id"],
                                    "npc_name": improvised_profile["name"],
                                    "improvised_profile_summary": {k:v for k,v in improvised_profile.items() if k not in ['initial_dialogue', 'appearance']},
                                    "triggering_thought_snippet": thought_context_text[:150],
                                    "scene_context_at_improvisation": scene_context,
                                    "timestamp": current_time_iso
                                }
                            }
                            EventBus.instance().publish(EVENT_MEMORY_WRITE, memory_payload)

                            original_thought = original_thought_payloads.get(thought_context_text, {})
                            new_npc_event_payload = {
                                "improvised_npc_profile": improvised_profile,
                                "triggering_thought_content": thought_context_text,
                                "original_subconscious_thought_payload": original_thought,
                                "scene_context_at_improvisation": scene_context
                            }
                            EventBus.instance().publish(NEW_NPC_IMPROVISED, new_npc_event_payload)
                            logger.info(f"Simulator: Published NEW_NPC_IMPROVISED event for NPC '{improvised_profile['name']}'.")
                        # else: logger.error(...) # Already logged by registry
                    # else: logger.warning(...) # Already logged by improviser or due to invalid profile

        except Exception as e: # pragma: no cover
            logger.error(f"Simulator: Error during subconscious NPC reference processing: {e}", exc_info=True)
    # else: logger.debug("NPC System not available...")

    # logger.debug("Simulator: Tick finished.")


if __name__ == '__main__': # pragma: no cover
    import unittest.mock
    from collections import defaultdict

    logging.basicConfig(level=logging.INFO)
    sim_logger = logging.getLogger('eidos_agent.features.firmament.core.simulator')
    sim_logger.setLevel(logging.DEBUG)

    _test_events_captured_sim = []
    def main_test_event_handler(event_type, data):
        _test_events_captured_sim.append({"type": event_type, "data": data})
        # Simplified print for __main__ to reduce noise
        print(f"    [SIM_MAIN_CAPTURE] Event: {event_type}, Main Data: {str(data.get('content', data.get('block', {}).get('name', data.get('improvised_npc_profile',{}).get('name', '...'))))[:60]}")


    if hasattr(EventBus, '_instance'): EventBus._instance = None
    test_bus_sim = EventBus.instance()
    if hasattr(test_bus_sim, '_subscribers'): test_bus_sim._subscribers = defaultdict(list)

    event_types_for_main_test = [
        SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED, WORLD_EVENT,
        THOUGHT_TRIGGER, EVENT_MEMORY_WRITE, NEW_NPC_IMPROVISED
    ]
    # Add IMPULSE and NPC_DIALOGUE only if they are actually defined (not dummies)
    if 'IMPULSE' in globals() and (not isinstance(globals()['IMPULSE'], str) or "dummy" not in str(globals().get('IMPULSE',''))):
        event_types_for_main_test.append(globals()['IMPULSE'])
    if 'NPC_DIALOGUE' in globals() and (not isinstance(globals()['NPC_DIALOGUE'], str) or "dummy" not in str(globals().get('NPC_DIALOGUE',''))):
        event_types_for_main_test.append(globals()['NPC_DIALOGUE'])

    for et_name_obj in event_types_for_main_test:
        actual_et_name_str = str(getattr(et_name_obj, 'value', et_name_obj))
        def create_main_handler(et_cap_name_str_arg): return lambda d: main_test_event_handler(et_cap_name_str_arg, d)
        test_bus_sim.subscribe(actual_et_name_str, create_main_handler(actual_et_name_str))

    mock_thoughts_main = [{'content': "Think of Cassandra.", 'timestamp': 'ts_main_test', 'source': 'main_test_subconscious'}]
    mock_profile_main = {"id": "cass_main_test", "name": "Cassandra Main Test Improv", "role": "Test Role"}

    class MockNPCRegistryMain:
        def __init__(self): self.npcs = {}; self.registered_npcs_in_test = []
        def get_all_npcs(self): return list(self.npcs.values())
        def register_npc(self, npc_data): self.registered_npcs_in_test.append(npc_data); return True
    mock_registry_main_inst = MockNPCRegistryMain()

    print("\n--- Testing Simulator Tick with ASYNC NPC Improvisation (via asyncio.run patch) ---")
    _current_active_block_data = None

    # Patch asyncio.run to check it's called and to control the return value for this __main__ test.
    # This avoids needing the NPCImproviser's mock to be an AsyncMock if it's complex for the tool,
    # and directly tests the asyncio.run integration point in the simulator.
    with patch('asyncio.run', return_value=mock_profile_main) as mock_asyncio_run, \
         patch('eidos_agent.features.firmament.core.simulator.NPC_SYSTEM_AVAILABLE', True), \
         patch('eidos_agent.features.firmament.core.simulator.get_recent_subconscious_thoughts', return_value=mock_thoughts_main) as m_get_thoughts, \
         patch('eidos_agent.features.firmament.core.simulator.extract_character_references', return_value=[("Cassandra", mock_thoughts_main[0]['content'])]) as m_extract_refs, \
         patch('eidos_agent.features.firmament.core.simulator.NPCRegistry.instance', return_value=mock_registry_main_inst) as m_registry_factory, \
         patch('eidos_agent.features.firmament.core.simulator.maybe_trigger_random_event') as m_random_events: # Mock random events

        # We need to ensure that the object passed to asyncio.run is an awaitable (coroutine).
        # The dummy NPCImproviser.improvise_npc is already async def.
        # If using the real NPCImproviser, its improvise_npc is also async def.

        # To ensure the `npc_improviser` instance used inside `run_simulation_tick` is the one we expect,
        # we can patch its instantiation if needed, or rely on the dummy for this __main__ test.
        # For this test, the dummy's async nature is sufficient if real imports fail.
        # If real imports succeed, the real async method will be called by asyncio.run.

        _set_current_block_for_testing({"id": "test_sim_block_async_improv", "name": "Activity Async Improv", "type": "testing"})
        run_simulation_tick()

    mock_asyncio_run.assert_called_once()
    # Check that the first argument to asyncio.run was a coroutine (has __await__ method)
    # This is a bit indirect but checks if an awaitable was passed.
    self_of_coro_passed_to_run = mock_asyncio_run.call_args[0][0]
    assert hasattr(self_of_coro_passed_to_run, '__await__'), "asyncio.run was not called with an awaitable (coroutine)."
    # To check if it was a method of NPCImproviser (if not using dummy):
    # if NPC_SYSTEM_AVAILABLE and not isinstance(NPCImproviser(), type(lambda:0)): # Check if real class
    #     assert isinstance(self_of_coro_passed_to_run.__self__, NPCImproviser), \
    #            "asyncio.run not called with NPCImproviser.improvise_npc method."


    assert len(mock_registry_main_inst.registered_npcs_in_test) == 1, \
        f"Expected 1 NPC registered, got {len(mock_registry_main_inst.registered_npcs_in_test)}"
    if mock_registry_main_inst.registered_npcs_in_test:
        assert mock_registry_main_inst.registered_npcs_in_test[0]['name'] == "Cassandra Main Test Improv"

    new_npc_events_main = [e for e in _test_events_captured_sim if e['type'] == str(NEW_NPC_IMPROVISED)]
    assert len(new_npc_events_main) == 1, f"Expected 1 NEW_NPC_IMPROVISED event in __main__, got {len(new_npc_events_main)}."
    if new_npc_events_main:
        assert new_npc_events_main[0]['data']['improvised_npc_profile']['id'] == "cass_main_test"

    print("Asyncio.run call for NPC improvisation in simulator tick (via __main__ patch) seems to work.")
    _current_active_block_data = None
    print("\n--- Simulator main test finished ---")
