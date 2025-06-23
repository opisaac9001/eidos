# eidos_agent/features/firmament/core/simulator.py
import logging
from datetime import datetime, timezone
import asyncio

from .event_bus import EventBus
from .event_types import SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED, WORLD_EVENT, THOUGHT_TRIGGER, NEW_NPC_IMPROVISED

# --- Integration Imports ---
from typing import Optional, Dict, Any, List # Ensure List is imported for type hints

# Import ChronosAdapter class instead of global functions
try:
    from ..integrations.chronos_adapter import ChronosAdapter
    from ....persona_logic.ethos_core.core import EthosCore
except ImportError: # pragma: no cover
    print("CRITICAL: Could not import ChronosAdapter or EthosCore. Simulator will use dummies.")
    class ChronosAdapter: # type: ignore
        def __init__(self, ethos_core_mock): pass # Add dummy __init__
        async def get_current_block(self):
            # logger is not defined at module level yet if this dummy is hit during initial imports
            print("Warning: Using DUMMY ChronosAdapter.get_current_block in simulator.")
            return {"id": "dummy_error_block_sim_ca", "name": "Dummy Error Block (CA missing)", "type": "error"}
    class EthosCore: # type: ignore
        PATHOS_USER_ID = "dummy_pathos_user_sim_import_error"
        ethos_config = {"pathos_home_timezone": "UTC"} # Dummy config
        async def get_local_datetime_for_user(self, user_id: str) -> datetime:
            return datetime.now(timezone.utc)
        def get_current_mood(self) -> Dict[str, Any]: # Added for NPC improvisation context
            print("Dummy EthosCore (simulator import error): get_current_mood called")
            return {"name": "dummy_neutral", "valence": 0.0, "arousal": 0.0}

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
    from ..npcs.npc_improviser import NPCImproviser # Ensure this is available
    from ..npcs.npc_registry import NPCRegistry
    NPC_SYSTEM_AVAILABLE = True
except ImportError as e: # pragma: no cover
    print(f"CRITICAL: Could not import NPC system components for simulator: {e}. NPC improvisation will be disabled.")
    get_recent_subconscious_thoughts = lambda limit=5: [] #type:ignore
    extract_character_references = lambda thoughts, known_profiles: [] #type:ignore
    class NPCImproviser: #type:ignore
        def __init__(self, firmament_llm_role_name: Optional[str] = None): # Match real signature better
            logger.warning(f"Using DUMMY NPCImproviser (role: {firmament_llm_role_name}) due to import error.")
        async def improvise_npc(self, name_hint, subconscious_thought_context, scene_context):
            logger.warning("DUMMY NPCImproviser.improvise_npc (async) called.");
            return {"id":"dummy_async_npc","name":name_hint or "DummyAsyncNPC", "role":"dummy_role"} if name_hint else None
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
PLUGIN_SYSTEM_AVAILABLE_SIM = False
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
_current_active_block_data: Optional[Dict[str, Any]] = None
EVENT_MEMORY_WRITE = "memory.write"

_ethos_core_instance_for_sim: Optional[EthosCore] = None
_npc_improviser_instance: Optional[NPCImproviser] = None
_chronos_adapter_instance: Optional[ChronosAdapter] = None # Module-level instance for ChronosAdapter

def set_ethos_core_for_simulator(ethos_core: EthosCore):
    global _ethos_core_instance_for_sim
    _ethos_core_instance_for_sim = ethos_core
    logger.info(f"Simulator: EthosCore instance set. {_ethos_core_instance_for_sim is not None}")

def set_npc_improviser_for_simulator(improviser: NPCImproviser):
    global _npc_improviser_instance
    _npc_improviser_instance = improviser
    logger.info(f"Simulator: NPCImproviser instance set. {_npc_improviser_instance is not None}")

def set_chronos_adapter_for_simulator(adapter: ChronosAdapter): # New setter for ChronosAdapter
    global _chronos_adapter_instance
    _chronos_adapter_instance = adapter
    logger.info(f"Simulator: ChronosAdapter instance set. {_chronos_adapter_instance is not None}")

async def run_simulation_tick():
    global _current_active_block_data
    current_time_iso_for_tick = datetime.now(timezone.utc).isoformat()

    # --- Schedule Block Transition Logic ---
    if not _chronos_adapter_instance:
        logger.error("Simulator: ChronosAdapter instance not set. Cannot get current block.")
        new_block_data = {"id": "error_no_chronos_adapter", "name": "Error: ChronosAdapter Missing", "type": "error", "description": "ChronosAdapter not set in simulator."}
    else:
        new_block_data = await _chronos_adapter_instance.get_current_block()

    if not isinstance(new_block_data, dict) or not new_block_data.get("id"):
        logger.warning(f"Simulator: Invalid or None block data received: {new_block_data}")
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
            if not _npc_improviser_instance:
                logger.error("Simulator: NPCImproviser instance not set. Skipping NPC improvisation from thoughts.")
            else:
                npc_improviser = _npc_improviser_instance
                registry = NPCRegistry.instance()
                recent_thoughts_data = get_recent_subconscious_thoughts(limit=5) # This is synchronous, returns List[Dict[str, Any]]
                if recent_thoughts_data:
                    # Use 'primary_display_content' and filter out None/empty strings
                    thought_contents = [t.get('primary_display_content') for t in recent_thoughts_data if isinstance(t, dict) and t.get('primary_display_content')]
                    thought_contents = [content for content in thought_contents if content and content.strip()]

                    # Use 'primary_display_content' as key for original_thought_payloads
                    original_thought_payloads = {t.get('primary_display_content'): t for t in recent_thoughts_data if isinstance(t, dict) and t.get('primary_display_content')}

                    known_npc_profiles = registry.get_all_npcs() # This is synchronous
                    new_references = extract_character_references(thought_contents, known_npc_profiles) # This is synchronous

                    for name_hint, thought_context_text in new_references:
                        logger.info(f"Simulator: New NPC reference detected: '{name_hint}' from thought: '{thought_context_text[:70]}...'")

                        location = _current_active_block_data.get('location_hint', _current_active_block_data.get('name', 'unknown_location')) if _current_active_block_data else 'an unspecified place'
                        activity = _current_active_block_data.get('name', 'an unknown activity') if _current_active_block_data else 'an unknown activity'

                        pathos_mood_name = "neutral"
                        if _ethos_core_instance_for_sim:
                            try:
                                mood_data = _ethos_core_instance_for_sim.get_current_mood() # Synchronous
                                if mood_data and isinstance(mood_data, dict) and "name" in mood_data:
                                    pathos_mood_name = mood_data["name"]
                                    logger.debug(f"Simulator: Fetched mood for NPC context: {pathos_mood_name}")
                                else:
                                    logger.warning(f"Simulator: Failed to get valid mood name from EthosCore for NPC context. Using default '{pathos_mood_name}'.")
                            except Exception as e_mood:
                                logger.error(f"Simulator: Error fetching mood from EthosCore for NPC context: {e_mood}", exc_info=True)
                                logger.info(f"Simulator: Using default mood '{pathos_mood_name}' due to error.")
                        else:
                            logger.warning("Simulator: EthosCore not available for mood fetching. Using default mood for NPC context.")

                        scene_context = {
                            "location_description": location,
                            "pathos_mood_state": pathos_mood_name,
                            "current_activity_name": activity,
                            "time_of_day": current_time_iso_for_tick,
                        }

                        improvised_profile = await npc_improviser.improvise_npc(name_hint, thought_context_text, scene_context) # Now awaited

                        if improvised_profile and isinstance(improvised_profile, dict) and improvised_profile.get("name") and improvised_profile.get("id"):
                            success = registry.register_npc(npc_data=improvised_profile) # Synchronous
                            if success:
                                logger.info(f"Simulator: Registered improvised NPC: '{improvised_profile['name']}' (ID: {improvised_profile['id']})")
                                memory_payload = {
                                    "type": "npc_improvised",
                                    "content": f"A new persona, '{improvised_profile['name']}' (ID: {improvised_profile['id']}), was improvised by Firmament based on a thought about '{name_hint}'. Role: {improvised_profile.get('role', 'N/A')}.",
                                    "metadata": { "npc_id": improvised_profile["id"], "npc_name": improvised_profile["name"],
                                                  "triggering_thought_snippet": thought_context_text[:150], "timestamp": current_time_iso_for_tick }}
                                EventBus.instance().publish(EVENT_MEMORY_WRITE, memory_payload) # Synchronous
                                original_thought = original_thought_payloads.get(thought_context_text, {})
                                new_npc_event_payload = {"improvised_npc_profile": improvised_profile, "triggering_thought_content": thought_context_text,
                                                         "original_subconscious_thought_payload": original_thought, "scene_context_at_improvisation": scene_context }
                                EventBus.instance().publish(NEW_NPC_IMPROVISED, new_npc_event_payload) # Synchronous
        except Exception as e: # pragma: no cover
            logger.error(f"Simulator: Error during subconscious NPC reference processing: {e}", exc_info=True)

    if PLUGIN_SYSTEM_AVAILABLE_SIM and callable(get_plugin_manager):
        plugin_mgr = get_plugin_manager()
        if plugin_mgr and hasattr(plugin_mgr, 'run_plugin_updates') and callable(plugin_mgr.run_plugin_updates):
            plugin_mgr.run_plugin_updates(current_time_iso_for_tick, _current_active_block_data) # Synchronous


if __name__ == '__main__': # pragma: no cover
    from unittest.mock import patch, AsyncMock, MagicMock
    from collections import defaultdict
    from datetime import timedelta # Added for MockActivitySlotForSimTest
    # Import the real ChronosAdapter for instantiation in test
    from ..integrations.chronos_adapter import ChronosAdapter as RealChronosAdapter
    # Import ActivitySlot for type hinting the mock, if available, otherwise use Any
    try:
        from ....persona_logic.chronos_engine.models import ActivitySlot as RealActivitySlotType
    except ImportError:
        RealActivitySlotType = Any # Fallback type


    logging.basicConfig(level=logging.INFO)
    sim_logger_main = logging.getLogger('eidos_agent.features.firmament.core.simulator')
    sim_logger_main.setLevel(logging.DEBUG)

    _test_events_captured_sim_main = []
    def main_test_event_handler_for_sim_async(event_type, data):
        _test_events_captured_sim_main.append({"type": event_type, "data": data})
        captured_event_summary = str(data.get('content', data.get('block', {}).get('name', data.get('improvised_npc_profile',{}).get('name', '...'))))[:60]
        sim_logger_main.info(f"    [SIM_MAIN_CAPTURE] Event: {event_type}, Summary: {captured_event_summary}")

    if hasattr(EventBus, '_instance'): EventBus._instance = None
    test_bus_sim_main_async = EventBus.instance()
    if hasattr(test_bus_sim_main_async, '_subscribers'): test_bus_sim_main_async._subscribers = defaultdict(list)

    event_types_for_main_testing_async = [
        SCHEDULE_BLOCK_STARTED, SCHEDULE_BLOCK_ENDED, WORLD_EVENT,
        THOUGHT_TRIGGER, EVENT_MEMORY_WRITE, NEW_NPC_IMPROVISED
    ]
    def is_valid_event_type(event_obj_or_str):
        if not event_obj_or_str: return False
        if hasattr(event_obj_or_str, 'value'): val = getattr(event_obj_or_str, 'value')
        elif isinstance(event_obj_or_str, str): val = event_obj_or_str
        else: return False
        return isinstance(val, str) and "dummy" not in val.lower()

    if 'IMPULSE' in globals() and is_valid_event_type(globals().get('IMPULSE')):
        event_types_for_main_testing_async.append(globals()['IMPULSE'])

    for et_name_obj_main_async in event_types_for_main_testing_async:
        actual_et_name_str_main_async = str(getattr(et_name_obj_main_async, 'value', et_name_obj_main_async))
        def create_main_test_handler_async(et_cap_name_str_arg):
            return lambda data_arg: main_test_event_handler_for_sim_async(et_cap_name_str_arg, data_arg)
        test_bus_sim_main_async.subscribe(actual_et_name_str_main_async, create_main_test_handler_async(actual_et_name_str_main_async))

    mock_thoughts_main_async = [
        {
            'id': 'sim_thought_for_npc_test_1',
            'type': 'thought',
            'timestamp': 'ts_main_test_async_sim',
            'primary_display_content': "Think of Cassandra for test.",
            'content': "Elaborated version: Think of Cassandra for test, perhaps she knows about the old library.",
            'metadata': {
                'raw_trigger_content': "Think of Cassandra for test.",
                'source': 'main_test_subconscious_simulator',
                'user_id': 'pathos_test_user_sim_main_async'
            },
            'salience': 0.85
        }
    ]
    mock_profile_main_async = {"id": "cass_async_direct_await", "name": "Cassandra DirectAwait Improv", "role": "DirectAwait Test Role"}

    class MockNPCRegistryMainSimAsync:
        def __init__(self): self.npcs_registered_in_test = {}; sim_logger_main.info("MockNPCRegistryMainSimAsync Initialized")
        def get_all_npcs(self): return list(self.npcs_registered_in_test.values())
        def register_npc(self, npc_data):
            npc_id = npc_data.get('id');
            if not npc_id: logger.error("MockNPCRegistryMainSimAsync: register_npc called with no ID."); return False
            self.npcs_registered_in_test[npc_id] = npc_data; return True
    mock_registry_main_inst_sim_async = MockNPCRegistryMainSimAsync()

    class MockEthosCoreForSimulator:
        PATHOS_USER_ID = "pathos_test_user_sim_main_async"
        # This mock EthosCore will now need a mock chronos_engine for the ChronosAdapter
        chronos_engine: Any = None # Will be set to MockSimChronosEngineForTest instance

        def __init__(self):
            self.ethos_config = {"pathos_home_timezone": "UTC"}
            sim_logger_main.info("MockEthosCoreForSimulator (async test) initialized.")

        def get_current_mood(self) -> Dict[str, Any]:
            sim_logger_main.info("MockEthosCoreForSimulator.get_current_mood called.")
            return {"name": "mocked_async_mood", "valence": 0.1, "arousal": 0.2}

        async def get_local_datetime_for_user(self, user_id: str) -> datetime:
            sim_logger_main.info(f"MockEthosCoreForSimulator.get_local_datetime_for_user for {user_id}")
            return datetime.now(timezone.utc)

    class MockNPCImproviser: # This mock can remain largely the same
        def __init__(self, firmament_llm_role_name=None):
            sim_logger_main.info(f"MockNPCImproviser (async test) initialized with role: {firmament_llm_role_name}")
        async def improvise_npc(self, name_hint, subconscious_thought_context, scene_context):
            sim_logger_main.info(f"MockNPCImproviser.improvise_npc called for {name_hint}")
            return mock_profile_main_async

    async def main_test_simulator_tick():
        global _current_active_block_data
        _current_active_block_data = None

        mock_ethos_sim_main = MockEthosCoreForSimulator()
        set_ethos_core_for_simulator(mock_ethos_sim_main)

        test_improviser = MockNPCImproviser() # This mock is fine
        set_npc_improviser_for_simulator(test_improviser)

        # NEW: Setup ChronosAdapter and its dependencies for the simulator test
        class MockActivitySlotForSimTest:
            def __init__(self, id, activity_type, activity_title, date, start_time, end_time, description="Desc", location="Loc", slot_name="Slot", status="pending"):
                self.id, self.activity_type, self.activity_title, self.date, self.start_time, self.end_time = id, activity_type, activity_title, date, start_time, end_time
                self.activity_details = type('details', (), {'description': description, 'location_context': location})()
                self.slot_name, self.status = slot_name, status

        class MockSimChronosEngineForTest:
            async def get_current_activity(self, current_datetime: datetime) -> Optional[MockActivitySlotForSimTest]:
                sim_logger_main.debug(f"MockSimChronosEngineForTest.get_current_activity called at {current_datetime}")
                # This is what ChronosAdapter's get_current_block will use
                return MockActivitySlotForSimTest(
                    id="test_sim_block_from_adapter", # New ID to confirm it's from this path
                    activity_type="testing_adapter",
                    activity_title="Activity Via Class Adapter", # New title
                    date=current_datetime.date(),
                    start_time=current_datetime.time(),
                    end_time=(current_datetime + timedelta(hours=1)).time()
                )

        mock_ethos_sim_main.chronos_engine = MockSimChronosEngineForTest()

        # Instantiate the real ChronosAdapter with the fully mocked EthosCore (which now has a mock chronos_engine)
        chronos_adapter_instance_for_test = RealChronosAdapter(ethos_core=mock_ethos_sim_main) # type: ignore
        set_chronos_adapter_for_simulator(chronos_adapter_instance_for_test)

        sim_logger_main.info("\n--- Testing Simulator Tick (Now Async, with Class-based ChronosAdapter) ---")

        # Remove the patch for the global get_current_block.
        # The test will now go through _chronos_adapter_instance.get_current_block()
        with patch('eidos_agent.features.firmament.core.simulator.NPC_SYSTEM_AVAILABLE', True), \
             patch('eidos_agent.features.firmament.core.simulator.get_recent_subconscious_thoughts', return_value=mock_thoughts_main_async), \
             patch('eidos_agent.features.firmament.core.simulator.extract_character_references', return_value=[("Cassandra", mock_thoughts_main_async[0]['content'])]), \
             patch('eidos_agent.features.firmament.core.simulator.NPCRegistry.instance', return_value=mock_registry_main_inst_sim_async), \
             patch('eidos_agent.features.firmament.core.simulator.maybe_trigger_random_event'), \
             patch('eidos_agent.features.firmament.core.simulator.get_plugin_manager', return_value=None):
            # NO MORE: patch('eidos_agent.features.firmament.integrations.chronos_adapter.get_current_block', ... )

            await run_simulation_tick()

        # Assertion for block data should reflect what MockSimChronosEngineForTest provides via ChronosAdapter
        block_started_events = [e for e in _test_events_captured_sim_main if e['type'] == str(SCHEDULE_BLOCK_STARTED)]
        assert len(block_started_events) > 0, "Expected SCHEDULE_BLOCK_STARTED event"
        if block_started_events:
            assert block_started_events[0]['data']['block']['id'] == "test_sim_block_from_adapter"
            assert block_started_events[0]['data']['block']['name'] == "Activity Via Class Adapter"

        assert len(mock_registry_main_inst_sim_async.npcs_registered_in_test) == 1, \
            f"Expected 1 NPC registered, got {len(mock_registry_main_inst_sim_async.npcs_registered_in_test)}"
        registered_npc_ids = list(mock_registry_main_inst_sim_async.npcs_registered_in_test.keys())
        assert mock_profile_main_async["id"] in registered_npc_ids, \
            f"Registered NPC ID mismatch. Expected '{mock_profile_main_async['id']}', found in {registered_npc_ids}"

        new_npc_events_main_async = [e for e in _test_events_captured_sim_main if e['type'] == str(NEW_NPC_IMPROVISED)]
        assert len(new_npc_events_main_async) == 1, f"Expected 1 NEW_NPC_IMPROVISED event, got {len(new_npc_events_main_async)}."
        if new_npc_events_main_async:
            assert new_npc_events_main_async[0]['data']['improvised_npc_profile']['id'] == mock_profile_main_async["id"]

        sim_logger_main.info("Async run_simulation_tick test completed. NPC Improvisation directly awaited.")
        _current_active_block_data = None
        sim_logger_main.info("\n--- Simulator main async test finished ---")

    asyncio.run(main_test_simulator_tick())
