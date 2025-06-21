# eidos_agent/features/firmament/integrations/chronos_adapter.py

# This module serves as an adapter to interface with the Chronos schedule engine.
# It will be responsible for fetching schedule information, such as current
# or upcoming blocks, and potentially for triggering or reacting to schedule changes.

# In a real system, this might involve API calls, database queries, or direct library usage
# to interact with the Chronos component.

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
import asyncio

try:
    from ....persona_logic.ethos_core.core import EthosCore
    from ....persona_logic.chronos_engine.models import ActivitySlot
    from .....persona_logic.chronos_engine import PATHOS_USER_ID # Added module level
    from datetime import time # Ensure time is imported for MockActivitySlot
    # Attempt to import ZoneInfo, fall back if not available (Python < 3.9)
    from zoneinfo import ZoneInfo
except ImportError: # pragma: no cover
    EthosCore = None # type: ignore
    ActivitySlot = None # type: ignore
    ZoneInfo = None # type: ignore
    PATHOS_USER_ID = "pathos_dummy_user_id_chronos_adapter" # Dummy for module level
    print("ChronosAdapter: Warning - Core Eidos components or ZoneInfo could not be imported. Using placeholders/dummies if defined or will raise errors.")
    # time would be missing here if datetime isn't fully imported, but test mocks need it.
    # However, datetime is already imported, so time should be accessible via datetime.time
    EventBus = None # Placeholder if import fails
    try:
        from ..core.event_bus import EventBus
    except ImportError:
        # logger is not defined yet at this point if this is the first import attempt
        print("ChronosAdapter Warning: Firmament EventBus could not be imported. Listener notifications will not be published in a real scenario.")
        # Define a dummy EventBus for the tests to run if the real one isn't available
        class DummyEventBus:
            _instance = None
            def __init__(self): self._subscribers = {}
            @classmethod
            def instance(cls):
                if cls._instance is None: cls._instance = cls()
                return cls._instance
            def publish(self, event_type, data): print(f"DummyEventBus: Published {event_type} with {data}") # Changed to print
            def subscribe(self, event_type, handler): pass
        EventBus = DummyEventBus # type: ignore


# Logger setup
import logging # Ensure logging is imported for the module level logger
logger = logging.getLogger(__name__)

# New Event Type String
FIRMAMENT_SCHEDULE_RELOAD_REQUESTED = "firmament.schedule_reload_requested"
# This should eventually move to firmament/core/event_types.py

# Required for type hints and new functions
from datetime import date
from typing import Coroutine, Any, Callable


class ChronosAdapter:
    def __init__(self, ethos_core: EthosCore):
        self.ethos_core = ethos_core
        self.logger = logging.getLogger(__name__)
        self.is_listening = False
        logger.info(f"ChronosAdapter initialized with EthosCore: {ethos_core is not None}")

    async def get_current_block(self) -> Optional[Dict[str, Any]]:
        if not self.ethos_core or not self.ethos_core.chronos_engine:
            self.logger.warning("ChronosAdapter Error: EthosCore or ChronosEngine not initialized.")
            return {"id": "error_no_ethos_chronos", "name": "Error: System Uninitialized", "type": "error", "description": "EthosCore/ChronosEngine missing."}

        try:
            pathos_id_to_use = getattr(self.ethos_core, 'PATHOS_USER_ID', PATHOS_USER_ID)

            pathos_local_now = await self.ethos_core.get_local_datetime_for_user(pathos_id_to_use)
            current_activity_slot: Optional[ActivitySlot] = await self.ethos_core.chronos_engine.get_current_activity(
                current_datetime=pathos_local_now
            )

            if current_activity_slot:
                pathos_tz_str = self.ethos_core.ethos_config.get('pathos_home_timezone', "UTC")
                pathos_tz = timezone.utc
                if ZoneInfo and pathos_tz_str.lower() != "utc":
                    try: pathos_tz = ZoneInfo(pathos_tz_str)
                    except Exception: self.logger.warning(f"Invalid timezone '{pathos_tz_str}'. Defaulting to UTC.")

                start_datetime_local = datetime.combine(current_activity_slot.date, current_activity_slot.start_time, tzinfo=pathos_tz)
                end_datetime_local = datetime.combine(current_activity_slot.date, current_activity_slot.end_time, tzinfo=pathos_tz)

                block_dict = {
                    "id": current_activity_slot.id,
                    "type": str(current_activity_slot.activity_type),
                    "name": current_activity_slot.activity_title,
                    "start_time_utc": start_datetime_local.astimezone(timezone.utc).isoformat(),
                    "end_time_utc": end_datetime_local.astimezone(timezone.utc).isoformat(),
                    "description": current_activity_slot.activity_details.description if current_activity_slot.activity_details else "",
                    "location_hint": current_activity_slot.activity_details.location_context if current_activity_slot.activity_details else None,
                    "slot_name": current_activity_slot.slot_name,
                    "status": current_activity_slot.status
                }
                return block_dict
            else:
                return {
                    "id": f"unscheduled_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                    "type": "unscheduled", "name": "Unscheduled Time / Idle",
                    "start_time_utc": datetime.now(timezone.utc).isoformat(),
                    "end_time_utc": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
                    "description": "Pathos is currently unscheduled or idle."
                }
        except Exception as e:
            self.logger.error(f"ChronosAdapter Error: Failed to get current block: {e}", exc_info=True)
            return {"id": "error_get_block_exception", "name": "Error Fetching Block", "type": "error", "description": str(e)}

    async def get_upcoming_blocks(self, count: int = 3) -> List[Dict[str, Any]]:
        if not self.ethos_core or not self.ethos_core.chronos_engine:
            self.logger.warning("ChronosAdapter Error: EthosCore or ChronosEngine not initialized.")
            return [{"id": f"error_upcoming_{i}", "name": "Error: System Uninitialized", "type": "error"} for i in range(count)]

        upcoming_blocks_dicts: List[Dict[str, Any]] = []
        pathos_id_to_use = getattr(self.ethos_core, 'PATHOS_USER_ID', PATHOS_USER_ID)

        try:
            pathos_local_now = await self.ethos_core.get_local_datetime_for_user(pathos_id_to_use)
            today_date = pathos_local_now.date()
            current_time = pathos_local_now.time()

            todays_schedule: List[ActivitySlot] = await self.ethos_core.chronos_engine.get_todays_schedule_for_user()

            pathos_tz_str = self.ethos_core.ethos_config.get('pathos_home_timezone', "UTC")
            pathos_tz = timezone.utc
            if ZoneInfo and pathos_tz_str.lower() != "utc":
                try: pathos_tz = ZoneInfo(pathos_tz_str)
                except Exception: self.logger.warning(f"Invalid timezone '{pathos_tz_str}'. Defaulting to UTC.")

            for slot in todays_schedule:
                if len(upcoming_blocks_dicts) >= count: break
                if slot.activity_details and slot.end_time > current_time: # Ensure activity_details exists
                    start_dt_local = datetime.combine(slot.date, slot.start_time, tzinfo=pathos_tz)
                    end_dt_local = datetime.combine(slot.date, slot.end_time, tzinfo=pathos_tz)
                    block_dict = {
                        "id": slot.id, "type": str(slot.activity_type), "name": slot.activity_title,
                        "start_time_utc": start_dt_local.astimezone(timezone.utc).isoformat(),
                        "end_time_utc": end_dt_local.astimezone(timezone.utc).isoformat(),
                        "description": slot.activity_details.description,
                        "location_hint": slot.activity_details.location_context,
                        "slot_name": slot.slot_name, "status": slot.status
                    }
                    upcoming_blocks_dicts.append(block_dict)

            if len(upcoming_blocks_dicts) < count:
                tomorrow_date = today_date + timedelta(days=1)
                self.logger.info(f"ChronosAdapter: Not enough blocks from today. Fetching schedule for tomorrow: {tomorrow_date.isoformat()}")
                tomorrows_schedule: List[ActivitySlot] = await self.ethos_core.chronos_engine.get_schedule_for_date(
                    target_date=tomorrow_date, user_id=pathos_id_to_use
                )
                for slot in tomorrows_schedule:
                    if len(upcoming_blocks_dicts) >= count: break
                    if slot.activity_details: # Ensure activity_details exists
                        start_dt_local = datetime.combine(slot.date, slot.start_time, tzinfo=pathos_tz)
                        end_dt_local = datetime.combine(slot.date, slot.end_time, tzinfo=pathos_tz)
                        block_dict = {
                            "id": slot.id, "type": str(slot.activity_type), "name": slot.activity_title,
                            "start_time_utc": start_dt_local.astimezone(timezone.utc).isoformat(),
                            "end_time_utc": end_dt_local.astimezone(timezone.utc).isoformat(),
                            "description": slot.activity_details.description,
                            "location_hint": slot.activity_details.location_context,
                            "slot_name": slot.slot_name, "status": slot.status
                        }
                        upcoming_blocks_dicts.append(block_dict)

            return upcoming_blocks_dicts[:count]
        except Exception as e:
            self.logger.error(f"ChronosAdapter Error: Failed to get upcoming blocks: {e}", exc_info=True)
            return [{"id": f"error_upcoming_{i}", "name": "Error Fetching Upcoming", "type": "error", "description": str(e)} for i in range(count)]

    async def _handle_firmament_schedule_update(self, affected_date: date, user_id: str):
        self.logger.info(f"ChronosAdapter: Received schedule update notification for date: {affected_date}, user: {user_id}. Publishing to Firmament EventBus.")
        pathos_id_to_use = getattr(self.ethos_core, 'PATHOS_USER_ID', PATHOS_USER_ID)
        if user_id == pathos_id_to_use:
            if EventBus is None:
                self.logger.error("ChronosAdapter: EventBus is None, cannot publish schedule update.")
                return
            try:
                firmament_event_bus = EventBus.instance()
                firmament_event_bus.publish(
                    FIRMAMENT_SCHEDULE_RELOAD_REQUESTED,
                    {"affected_date": affected_date.isoformat(), "user_id": user_id, "reason": "chronos_schedule_updated"}
                )
                self.logger.info(f"ChronosAdapter: Published '{FIRMAMENT_SCHEDULE_RELOAD_REQUESTED}' for date: {affected_date}, user: {user_id}.")
            except Exception as e:
                self.logger.error(f"ChronosAdapter: Failed to publish schedule update to Firmament EventBus: {e}", exc_info=True)
        else:
            self.logger.debug(f"ChronosAdapter: Received schedule update for user '{user_id}', but only processing for '{pathos_id_to_use}'. Ignoring.")

    async def start_listening_to_schedule_updates(self) -> bool:
        """Registers the adapter's handler with ChronosEngine's schedule update notifications."""
        if not self.ethos_core or not hasattr(self.ethos_core, 'chronos_engine') or not self.ethos_core.chronos_engine:
            self.logger.error("ChronosAdapter: Cannot subscribe - EthosCore or ChronosEngine not initialized.")
            return False
        if not hasattr(self.ethos_core.chronos_engine, 'register_schedule_update_listener'):
            self.logger.error("ChronosAdapter: ChronosEngine missing 'register_schedule_update_listener'.")
            return False
        try:
            self.ethos_core.chronos_engine.register_schedule_update_listener(self._handle_firmament_schedule_update)
            self.is_listening = True
            self.logger.info("ChronosAdapter: Successfully subscribed to ChronosEngine schedule updates.")
            return True
        except Exception as e:
            self.logger.error(f"ChronosAdapter: Error subscribing to ChronosEngine updates: {e}", exc_info=True)
            return False

    async def stop_listening_to_schedule_updates(self):
        """Unregisters the adapter's handler from ChronosEngine."""
        if self.is_listening and self.ethos_core and hasattr(self.ethos_core, 'chronos_engine') and self.ethos_core.chronos_engine and \
           hasattr(self.ethos_core.chronos_engine, 'unregister_schedule_update_listener'):
            try:
                self.ethos_core.chronos_engine.unregister_schedule_update_listener(self._handle_firmament_schedule_update)
                self.is_listening = False
                self.logger.info("ChronosAdapter: Unsubscribed from ChronosEngine schedule updates.")
            except Exception as e:
                self.logger.error(f"ChronosAdapter: Error unsubscribing from ChronosEngine updates: {e}", exc_info=True)
        elif self.is_listening:
            self.logger.warning("ChronosAdapter: Could not unsubscribe, dependencies missing or listener not active.")


if __name__ == '__main__':
    import unittest.mock # For __main__ tests
    from datetime import date # For __main__ tests (already imported above too)

    # Ensure logging is configured for the test run
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger_main = logging.getLogger("chronos_adapter_main_test") # Use a specific logger for main
    logger_main.info("--- Testing Chronos Adapter (Async) ---")

    # Mock ActivitySlot and EthosCore for testing
    class MockActivitySlot:
        def __init__(self, id, activity_type, activity_title, date, start_time, end_time, description="Desc", location="Loc", slot_name="Slot", status="pending"):
            self.id = id
            self.activity_type = activity_type
            self.activity_title = activity_title
            self.date = date
            self.start_time = start_time
            self.end_time = end_time
            # Mocking activity_details as an object with attributes
            self.activity_details = type('ActivityDetails', (), {})()
            self.activity_details.description = description
            self.activity_details.location_context = location
            self.slot_name = slot_name
            self.status = status

    class MockChronosEngine:
        def __init__(self, parent_ethos_core: 'MockEthosCore'): # Store parent to access its methods if needed
            self.parent_ethos_core = parent_ethos_core

        async def get_current_activity(self, current_datetime: datetime) -> Optional[MockActivitySlot]:
            logger.info(f"MockChronosEngine.get_current_activity called with time: {current_datetime}")
            return MockActivitySlot(
                id="mock_slot_123", activity_type="testing", activity_title="Mocked Activity from Chronos",
                date=current_datetime.date(), start_time=current_datetime.time(),
                end_time=(current_datetime + timedelta(hours=1)).time(),
                description="This is a mocked activity for testing ChronosAdapter."
            )

        async def get_todays_schedule_for_user(self) -> List[MockActivitySlot]:
            logger.info(f"MockChronosEngine.get_todays_schedule_for_user called.")
            now = await self.parent_ethos_core.get_local_datetime_for_user(PATHOS_USER_ID)
            return [
                MockActivitySlot("slot_future_today", "learning", "Future Learning Today", now.date(), (now + timedelta(hours=1)).time(), (now + timedelta(hours=2)).time())
            ]

        async def get_schedule_for_date(self, target_date: date, user_id: str) -> List[MockActivitySlot]:
            logger.info(f"MockChronosEngine.get_schedule_for_date called for date {target_date}, user {user_id}")
            now = await self.parent_ethos_core.get_local_datetime_for_user(user_id)
            if target_date == (now.date() + timedelta(days=1)): # Tomorrow
                return [
                    MockActivitySlot("slot_tomorrow1", "work", "Work Tomorrow", target_date, time(9,0), time(10,0)),
                    MockActivitySlot("slot_tomorrow2", "leisure", "Leisure Tomorrow", target_date, time(10,0), time(11,0))
                ]
            return []


    class MockEthosCore:
        PATHOS_USER_ID = "pathos_test_user_chronos_adapter" # Define for the mock

        def __init__(self):
            self.chronos_engine = MockChronosEngine(self) # Pass self to MockChronosEngine
            # Mock ethos_config as a simple dictionary for testing
            self.ethos_config = {"pathos_home_timezone": "America/New_York"}

        async def get_local_datetime_for_user(self, user_id: str) -> datetime:
            logger.info(f"MockEthosCore.get_local_datetime_for_user called for {user_id}")
            assert user_id == self.PATHOS_USER_ID # Use the class attribute for assertion
            tz_str = self.ethos_config.get('pathos_home_timezone', "UTC")
            tz = timezone.utc # Default
            if ZoneInfo and tz_str.lower() != "utc":
                try:
                    tz = ZoneInfo(tz_str)
                except Exception as e_tz:
                    logger.warning(f"MockEthosCore Warning: Could not use timezone '{tz_str}': {e_tz}")
            return datetime.now(tz)

    # Setup for the test
    mock_ethos_instance = MockEthosCore()
    set_ethos_core_for_chronos_adapter(mock_ethos_instance)

    # Test runner function
    async def main_tests():
        logger_main.info("\n1. Testing get_current_block() with mocked EthosCore and ChronosEngine:")
        current_block_via_ethos = await get_current_block() # Now async
        if current_block_via_ethos:
            logger_main.info("   Current Schedule Block (via mocked EthosCore):")
            for key, value in current_block_via_ethos.items():
                logger_main.info(f"     {key}: {value}")
            assert current_block_via_ethos["id"] == "mock_slot_123"
            assert current_block_via_ethos["name"] == "Mocked Activity from Chronos"
            assert "start_time_utc" in current_block_via_ethos
        else:
            logger_main.error("   get_current_block() returned None or an error block.")

        logger_main.info("\n2. Overriding current block for testing (still works):")
        test_override_block = {
            "id": "test_block_override_789", "type": "testing_override",
            "name": "Chronos Adapter Test Override Block",
            "start_time_utc": datetime.now(timezone.utc).isoformat(),
            "end_time_utc": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "description": "This block is from _set_current_block_for_testing."
        }
        _set_current_block_for_testing(test_override_block)
        current_block_overridden = await get_current_block() # Now async
        logger_main.info("   Current Schedule Block (Overridden for Test):")
        if current_block_overridden:
            for key, value in current_block_overridden.items():
                logger_main.info(f"     {key}: {value}")
            assert current_block_overridden["id"] == "test_block_override_789"
        _set_current_block_for_testing(None)

        logger_main.info("\n3. Testing get_current_block() after reset (should use mock Ethos again):")
        current_block_after_reset = await get_current_block() # Now async
        if current_block_after_reset:
            logger_main.info("   Current Schedule Block (via mocked EthosCore after reset):")
            for key, value in current_block_after_reset.items():
                logger_main.info(f"     {key}: {value}")
            assert current_block_after_reset["id"] == "mock_slot_123"
        else:
            logger_main.info("   get_current_block() returned None or an error block after reset.")

        logger_main.info("\n--- Testing get_upcoming_blocks ---")
        upcoming = await get_upcoming_blocks(2) # Now async
        logger_main.info(f"Upcoming blocks retrieved: {len(upcoming)}")
        assert len(upcoming) <= 2, f"Expected 2 or fewer upcoming blocks, got {len(upcoming)}"
        if len(upcoming) > 0:
            first_upcoming_name = upcoming[0]["name"]
            logger_main.info(f"First upcoming block name: {first_upcoming_name}")
            assert "Tomorrow" in first_upcoming_name # Adjusted for clarity based on mock
        if len(upcoming) == 2:
             second_upcoming_name = upcoming[1]["name"]
             logger_main.info(f"Second upcoming block name: {second_upcoming_name}")
             assert "Tomorrow" in second_upcoming_name


        # --- Testing Schedule Update Subscription and Handling ---
        logger_main.info("\n--- Testing Schedule Update Subscription and Handling ---")

        mock_firmament_event_bus_publish = unittest.mock.MagicMock()
        original_event_bus_instance_method = EventBus.instance
        EventBus.instance = unittest.mock.MagicMock(return_value=unittest.mock.MagicMock(publish=mock_firmament_event_bus_publish))

        captured_listener_arg = None
        def mock_register_listener(listener_func):
            nonlocal captured_listener_arg
            captured_listener_arg = listener_func
            logger_main.info(f"MockChronosEngine: Listener {getattr(listener_func,'__name__','<unknown>')} registered.")

        mock_ethos_instance.chronos_engine.register_schedule_update_listener = mock_register_listener

        subscribe_success = subscribe_to_schedule_updates()
        assert subscribe_success, "Failed to subscribe to schedule updates."
        assert captured_listener_arg is not None, "Listener was not captured by mock_register_listener."
        assert captured_listener_arg == _firmament_schedule_update_handler, "Incorrect listener was registered."

        if captured_listener_arg:
            test_update_date = date(2024, 7, 4)
            test_update_user = PATHOS_USER_ID # Use the one the handler checks against

            logger_main.info(f"Simulating call to captured listener with date: {test_update_date}, user: {test_update_user}")
            await captured_listener_arg(test_update_date, test_update_user)

            mock_firmament_event_bus_publish.assert_called_once()
            args, _ = mock_firmament_event_bus_publish.call_args
            assert args[0] == FIRMAMENT_SCHEDULE_RELOAD_REQUESTED
            assert args[1]["affected_date"] == test_update_date.isoformat()
            assert args[1]["user_id"] == test_update_user
            logger_main.info("Schedule update handler correctly published to Firmament EventBus.")

        EventBus.instance = original_event_bus_instance_method # Restore

        logger_main.info("\n--- Chronos Adapter testing finished ---")

    asyncio.run(main_tests())
