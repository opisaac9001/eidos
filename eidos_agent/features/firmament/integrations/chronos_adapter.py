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


_ethos_core_instance: Optional[EthosCore] = None
_current_block_override: Optional[Dict[str, Any]] = None # For testing purposes, type hinted

# Logger setup
logger = logging.getLogger(__name__) # Added logger

def set_ethos_core_for_chronos_adapter(ethos_core: EthosCore):
    global _ethos_core_instance
    _ethos_core_instance = ethos_core
    logger.info(f"ChronosAdapter: EthosCore instance set. EthosCore is present: {_ethos_core_instance is not None}")
    if _ethos_core_instance:
        logger.info(f"ChronosAdapter: EthosCore.chronos_engine is present: {_ethos_core_instance.chronos_engine is not None}")


def get_current_block() -> Optional[Dict[str, Any]]:
    """
    Fetches the current schedule block for Pathos from ChronosEngine via EthosCore.
    Returns the block data as a dictionary, or None if not found or error.
    """
    global _current_block_override
    if _current_block_override:
        logger.debug("ChronosAdapter: get_current_block() called (returning overridden block for testing)")
        return _current_block_override

    if not _ethos_core_instance or not _ethos_core_instance.chronos_engine:
        logger.error("ChronosAdapter Error: EthosCore or ChronosEngine not initialized. Cannot get current block.")
        return {"id": "error_no_ethos_chronos", "name": "Error: System Uninitialized", "type": "error", "description": "EthosCore/ChronosEngine missing."}

    try:
        async def _async_get_block() -> Optional[ActivitySlot]:
            pathos_id_to_use = PATHOS_USER_ID # Use module-level imported PATHOS_USER_ID
            if hasattr(_ethos_core_instance, 'PATHOS_USER_ID') and _ethos_core_instance.PATHOS_USER_ID != PATHOS_USER_ID:
                logger.warning(f"ChronosAdapter: EthosCore's PATHOS_USER_ID ({_ethos_core_instance.PATHOS_USER_ID}) differs from imported ({PATHOS_USER_ID}). Using imported.")

            pathos_local_now = await _ethos_core_instance.get_local_datetime_for_user(
                pathos_id_to_use
            )
            current_activity_slot: Optional[ActivitySlot] = await _ethos_core_instance.chronos_engine.get_current_activity(
                current_datetime=pathos_local_now
            )
            return current_activity_slot

        current_slot: Optional[ActivitySlot] = asyncio.run(_async_get_block())

        if current_slot:
            pathos_tz_str = _ethos_core_instance.ethos_config.get('pathos_home_timezone', "UTC")
            pathos_tz = timezone.utc
            if ZoneInfo and pathos_tz_str.lower() != "utc":
                try:
                    pathos_tz = ZoneInfo(pathos_tz_str)
                except Exception:
                    logger.warning(f"ChronosAdapter Warning: Invalid timezone '{pathos_tz_str}'. Defaulting to UTC.")
                    pass

            start_datetime_local = datetime.combine(current_slot.date, current_slot.start_time, tzinfo=pathos_tz)
            end_datetime_local = datetime.combine(current_slot.date, current_slot.end_time, tzinfo=pathos_tz)

            block_dict = {
                "id": current_slot.id,
                "type": str(current_slot.activity_type),
                "name": current_slot.activity_title,
                "start_time_utc": start_datetime_local.astimezone(timezone.utc).isoformat(),
                "end_time_utc": end_datetime_local.astimezone(timezone.utc).isoformat(),
                "description": current_slot.activity_details.description if current_slot.activity_details else "",
                "location_hint": current_slot.activity_details.location_context if current_slot.activity_details else None,
                "slot_name": current_slot.slot_name,
                "status": current_slot.status,
            }
            logger.debug(f"ChronosAdapter: Returning current block: {block_dict.get('name')}")
            return block_dict
        else:
            logger.debug("ChronosAdapter: No current activity slot found for Pathos.")
            return {
                "id": f"unscheduled_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                "type": "unscheduled",
                "name": "Unscheduled Time / Idle",
                "start_time_utc": datetime.now(timezone.utc).isoformat(),
                "end_time_utc": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
                "description": "Pathos is currently unscheduled or idle."
            }
    except Exception as e:
        logger.error(f"ChronosAdapter Error: Failed to get current block: {e}", exc_info=True)
        return {"id": "error_get_block_exception", "name": "Error Fetching Block", "type": "error", "description": str(e)}

# --- Other potential Chronos interactions (placeholders) ---

def get_upcoming_blocks(count: int = 3) -> List[Dict[str, Any]]:
    """
    Fetches a list of upcoming schedule blocks for Pathos.
    Combines today's remaining schedule with tomorrow's schedule if needed.
    """
    if not _ethos_core_instance or not _ethos_core_instance.chronos_engine:
        logger.warning("ChronosAdapter Error: EthosCore or ChronosEngine not initialized. Cannot get upcoming blocks.")
        return [{"id": f"error_upcoming_{i}", "name": "Error: System Uninitialized", "type": "error"} for i in range(count)]

    upcoming_blocks_dicts: List[Dict[str, Any]] = []

    try:
        # This function is synchronous, but EthosCore/ChronosEngine methods are async.
        # Use asyncio.run() as a temporary bridge, similar to get_current_block.
        async def _async_get_upcoming():
            nonlocal upcoming_blocks_dicts # Allow modification of outer scope variable

            pathos_id_to_use = PATHOS_USER_ID # Use module-level imported PATHOS_USER_ID

            pathos_local_now = await _ethos_core_instance.get_local_datetime_for_user(pathos_id_to_use)
            today_date = pathos_local_now.date()
            current_time = pathos_local_now.time()

            todays_schedule: List[ActivitySlot] = await _ethos_core_instance.chronos_engine.get_todays_schedule_for_user()

            # Filter today's schedule for remaining blocks
            for slot in todays_schedule:
                if len(upcoming_blocks_dicts) >= count: break
                if slot.end_time > current_time: # Block ends after current time
                    pathos_tz_str = _ethos_core_instance.ethos_config.get('pathos_home_timezone', "UTC")
                    pathos_tz = timezone.utc
                    if ZoneInfo and pathos_tz_str.lower() != "utc":
                        try: pathos_tz = ZoneInfo(pathos_tz_str)
                        except Exception: pass

                    start_dt_local = datetime.combine(slot.date, slot.start_time, tzinfo=pathos_tz)
                    end_dt_local = datetime.combine(slot.date, slot.end_time, tzinfo=pathos_tz)
                    block_dict = {
                        "id": slot.id, "type": str(slot.activity_type), "name": slot.activity_title,
                        "start_time_utc": start_dt_local.astimezone(timezone.utc).isoformat(),
                        "end_time_utc": end_dt_local.astimezone(timezone.utc).isoformat(),
                        "description": slot.activity_details.description if slot.activity_details else "",
                        "location_hint": slot.activity_details.location_context if slot.activity_details else None,
                        "slot_name": slot.slot_name, "status": slot.status
                    }
                    upcoming_blocks_dicts.append(block_dict)

            if len(upcoming_blocks_dicts) < count:
                tomorrow_date = today_date + timedelta(days=1)
                logger.info(f"ChronosAdapter: Not enough blocks from today. Fetching schedule for tomorrow: {tomorrow_date.isoformat()}")

                # Ensure CHRONOS_PATHOS_USER_ID is defined in this scope; using pathos_id_to_use which is PATHOS_USER_ID
                tomorrows_schedule: List[ActivitySlot] = await _ethos_core_instance.chronos_engine.get_schedule_for_date(
                    target_date=tomorrow_date,
                    user_id=pathos_id_to_use
                )

                for slot in tomorrows_schedule:
                    if len(upcoming_blocks_dicts) >= count:
                        break
                    # Convert slot to dict and append (use the same conversion logic as for today's slots)
                    pathos_tz_str = _ethos_core_instance.ethos_config.get('pathos_home_timezone', "UTC")
                    pathos_tz = timezone.utc
                    if ZoneInfo and pathos_tz_str.lower() != "utc":
                        try: pathos_tz = ZoneInfo(pathos_tz_str)
                        except Exception: pass

                    start_dt_local = datetime.combine(slot.date, slot.start_time, tzinfo=pathos_tz)
                    end_dt_local = datetime.combine(slot.date, slot.end_time, tzinfo=pathos_tz)
                    block_dict = {
                        "id": slot.id, "type": str(slot.activity_type), "name": slot.activity_title,
                        "start_time_utc": start_dt_local.astimezone(timezone.utc).isoformat(),
                        "end_time_utc": end_dt_local.astimezone(timezone.utc).isoformat(),
                        "description": slot.activity_details.description if slot.activity_details else "",
                        "location_hint": slot.activity_details.location_context if slot.activity_details else None,
                        "slot_name": slot.slot_name, "status": slot.status
                    }
                    upcoming_blocks_dicts.append(block_dict)

        asyncio.run(_async_get_upcoming())
        return upcoming_blocks_dicts[:count]

    except Exception as e:
        logger.error(f"ChronosAdapter Error: Failed to get upcoming blocks: {e}", exc_info=True)
        return [{"id": f"error_upcoming_{i}", "name": "Error Fetching Upcoming", "type": "error", "description": str(e)} for i in range(count)]


def on_schedule_updated(handler_callback: callable):
    """
    Placeholder to register a callback for when the schedule is updated in Chronos.
    This would be used if Chronos supports a push mechanism for updates.
    """
    print(f"ChronosAdapter: on_schedule_updated registered callback {handler_callback.__name__} (placeholder)")
    # In a real system, this might add the callback to a list of listeners
    # that Chronos invokes when changes occur.
    pass

# --- Test Utilities ---
def _set_current_block_for_testing(block_data: dict = None):
    """
    Allows tests to override the block returned by get_current_block.
    Pass None to reset to default behavior.
    """
    global _current_block_override
    _current_block_override = block_data
    if block_data:
        print(f"ChronosAdapter Test Util: Current block is NOW OVERRIDDEN for get_current_block().")
    else:
        print(f"ChronosAdapter Test Util: Current block override REMOVED for get_current_block().")


if __name__ == '__main__':
    print("--- Testing Chronos Adapter ---")

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

    logger.info("\n1. Testing get_current_block() with mocked EthosCore and ChronosEngine:")
    current_block_via_ethos = get_current_block()
    if current_block_via_ethos:
        logger.info("   Current Schedule Block (via mocked EthosCore):")
        for key, value in current_block_via_ethos.items():
            logger.info(f"     {key}: {value}")
        assert current_block_via_ethos["id"] == "mock_slot_123"
        assert current_block_via_ethos["name"] == "Mocked Activity from Chronos"
        assert "start_time_utc" in current_block_via_ethos # Check for UTC conversion
    else:
        logger.error("   get_current_block() returned None or an error block.")


    logger.info("\n2. Overriding current block for testing (still works):")
    test_override_block = {
        "id": "test_block_override_789", "type": "testing_override",
        "name": "Chronos Adapter Test Override Block",
        "start_time_utc": datetime.now(timezone.utc).isoformat(),
        "end_time_utc": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "description": "This block is from _set_current_block_for_testing."
    }
    _set_current_block_for_testing(test_override_block)
    current_block_overridden = get_current_block()
    print("   Current Schedule Block (Overridden for Test):")
    if current_block_overridden:
        for key, value in current_block_overridden.items():
            print(f"     {key}: {value}")
        assert current_block_overridden["id"] == "test_block_override_789"
    _set_current_block_for_testing(None) # Reset override

    logger.info("\n3. Testing get_current_block() after reset (should use mock Ethos again):")
    current_block_after_reset = get_current_block()
    if current_block_after_reset:
        print("   Current Schedule Block (via mocked EthosCore after reset):")
        for key, value in current_block_after_reset.items():
            print(f"     {key}: {value}")
        assert current_block_after_reset["id"] == "mock_slot_123"
    else:
        print("   get_current_block() returned None or an error block after reset.")

    logger.info("\n--- Testing get_upcoming_blocks ---")
    upcoming = get_upcoming_blocks(2) # Request 2 upcoming blocks
    logger.info(f"Upcoming blocks retrieved: {upcoming}")
    assert len(upcoming) <= 2, f"Expected 2 or fewer upcoming blocks, got {len(upcoming)}"
    if len(upcoming) > 0:
        # Based on MockChronosEngine, first upcoming should be "Current Leisure for Upcoming" or "Future Learning 1"
        # This depends on the exact time the test is run relative to now_for_schedule in the mock
        # A more robust test might fix the "now" time for MockChronosEngine or check IDs.
        first_upcoming_name = upcoming[0]["name"]
        logger.info(f"First upcoming block name: {first_upcoming_name}")
        assert first_upcoming_name in ["Current Leisure for Upcoming", "Future Learning 1"], f"Unexpected first upcoming block: {first_upcoming_name}"
        if len(upcoming) == 2:
             second_upcoming_name = upcoming[1]["name"]
             logger.info(f"Second upcoming block name: {second_upcoming_name}")
             assert second_upcoming_name in ["Future Learning 1", "Future Creative"], f"Unexpected second upcoming block: {second_upcoming_name}"


    logger.info("\n--- Chronos Adapter testing finished ---")
