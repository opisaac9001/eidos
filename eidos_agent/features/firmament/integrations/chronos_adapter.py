# eidos_agent/features/firmament/integrations/chronos_adapter.py
import asyncio
import logging
from datetime import datetime, timezone, timedelta, date, time
from typing import Optional, Dict, Any, List, Coroutine, Callable

try:
    from ....persona_logic.ethos_core.core import EthosCore
    from ....persona_logic.chronos_engine.models import ActivitySlot
    from .....persona_logic.chronos_engine import PATHOS_USER_ID
    from zoneinfo import ZoneInfo
except ImportError: # pragma: no cover
    EthosCore = None # type: ignore
    ActivitySlot = None # type: ignore
    ZoneInfo = None # type: ignore
    PATHOS_USER_ID = "pathos_dummy_user_id_chronos_adapter"
    print("ChronosAdapter: Warning - Core Eidos components or ZoneInfo could not be imported.")

# Attempt to import Firmament's EventBus, with a dummy fallback for standalone testing
try:
    from ..core.event_bus import EventBus
except ImportError:
    print("ChronosAdapter Warning: Firmament EventBus could not be imported. Listener notifications will not be published in a real scenario.")
    class DummyEventBus:
        _instance = None
        def __init__(self): self._subscribers = {}
        @classmethod
        def instance(cls):
            if cls._instance is None: cls._instance = cls()
            return cls._instance
        def publish(self, event_type, data): logger.info(f"DummyEventBus: Published {event_type} with {data}")
        def subscribe(self, event_type, handler): pass
    EventBus = DummyEventBus # type: ignore

from ..core.event_types import FIRMAMENT_SCHEDULE_RELOAD_REQUESTED

logger = logging.getLogger(__name__)

class ChronosAdapter:
    def __init__(self, ethos_core: EthosCore):
        self.ethos_core = ethos_core
        self.logger = logging.getLogger(__name__)
        self.is_listening = False
        self.logger.info(f"ChronosAdapter initialized with EthosCore: {ethos_core is not None}")
        if self.ethos_core:
             self.logger.info(f"ChronosAdapter: EthosCore.chronos_engine is present: {hasattr(self.ethos_core, 'chronos_engine') and self.ethos_core.chronos_engine is not None}")


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
                # Ensure activity_details exists before trying to access attributes from it
                if slot.activity_details and slot.end_time > current_time:
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

        # Use PATHOS_USER_ID from ChronosEngine via EthosCore if available, else module-level one
        pathos_id_to_use = getattr(self.ethos_core, 'PATHOS_USER_ID', PATHOS_USER_ID)

        if user_id == pathos_id_to_use:
            if EventBus is None: # Should be caught by class init logging if this happens
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
            # register_schedule_update_listener is synchronous in ChronosEngine
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
                # unregister_schedule_update_listener is synchronous in ChronosEngine
                self.ethos_core.chronos_engine.unregister_schedule_update_listener(self._handle_firmament_schedule_update)
                self.is_listening = False
                self.logger.info("ChronosAdapter: Unsubscribed from ChronosEngine schedule updates.")
            except Exception as e:
                self.logger.error(f"ChronosAdapter: Error unsubscribing from ChronosEngine updates: {e}", exc_info=True)
        elif self.is_listening: # If is_listening is true but conditions to unregister aren't met
            self.logger.warning("ChronosAdapter: Could not unsubscribe, dependencies missing or listener was not active as expected.")
            self.is_listening = False # Reset state


if __name__ == '__main__':
    import unittest.mock
    from datetime import date, time # Ensure time is imported for MockActivitySlot

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger_main = logging.getLogger("chronos_adapter_main_test")
    logger_main.info("--- Testing Chronos Adapter (Async, Class-based) ---")

    class MockActivitySlot: # Renamed to avoid conflict if real one is somehow available
        def __init__(self, id, activity_type, activity_title, date_val, start_time_val, end_time_val, description="Desc", location="Loc", slot_name="Slot", status="pending"):
            self.id = id
            self.activity_type = activity_type
            self.activity_title = activity_title
            self.date = date_val # Changed name to avoid conflict
            self.start_time = start_time_val # Changed name
            self.end_time = end_time_val # Changed name
            self.activity_details = type('ActivityDetails', (), {})()
            self.activity_details.description = description
            self.activity_details.location_context = location
            self.slot_name = slot_name
            self.status = status

    class MockChronosEngineForAdapterTest:
        def __init__(self, parent_ethos_core):
            self.parent_ethos_core = parent_ethos_core
            self._registered_listeners = []

        async def get_current_activity(self, current_datetime: datetime) -> Optional[MockActivitySlot]:
            logger_main.info(f"MockChronosEngine.get_current_activity called with time: {current_datetime}")
            return MockActivitySlot(
                id="mock_slot_123", activity_type="testing", activity_title="Mocked Activity from Chronos",
                date_val=current_datetime.date(), start_time_val=current_datetime.time(),
                end_time_val=(current_datetime + timedelta(hours=1)).time(),
                description="This is a mocked activity for testing ChronosAdapter."
            )

        async def get_todays_schedule_for_user(self) -> List[MockActivitySlot]:
            logger_main.info(f"MockChronosEngine.get_todays_schedule_for_user called.")
            now_val = await self.parent_ethos_core.get_local_datetime_for_user(PATHOS_USER_ID)
            return [
                MockActivitySlot("slot_future_today", "learning", "Future Learning Today", now_val.date(), (now_val + timedelta(hours=1)).time(), (now_val + timedelta(hours=2)).time())
            ]

        async def get_schedule_for_date(self, target_date: date, user_id: str) -> List[MockActivitySlot]:
            logger_main.info(f"MockChronosEngine.get_schedule_for_date called for date {target_date}, user {user_id}")
            now_val = await self.parent_ethos_core.get_local_datetime_for_user(user_id)
            if target_date == (now_val.date() + timedelta(days=1)): # Tomorrow
                return [
                    MockActivitySlot("slot_tomorrow1", "work", "Work Tomorrow", target_date, time(9,0), time(10,0)),
                    MockActivitySlot("slot_tomorrow2", "leisure", "Leisure Tomorrow", target_date, time(10,0), time(11,0))
                ]
            return []

        def register_schedule_update_listener(self, listener_func): # Mock sync version
            self._registered_listeners.append(listener_func)
            logger_main.info(f"MockChronosEngine: Listener {getattr(listener_func,'__name__','<unknown>')} registered.")

        def unregister_schedule_update_listener(self, listener_func): # Mock sync version
            try:
                self._registered_listeners.remove(listener_func)
                logger_main.info(f"MockChronosEngine: Listener {getattr(listener_func,'__name__','<unknown>')} unregistered.")
            except ValueError:
                logger_main.warning(f"MockChronosEngine: Attempted to unregister listener not found.")


    class MockEthosCoreForAdapterTest:
        PATHOS_USER_ID = "pathos_test_user_chronos_adapter"

        def __init__(self):
            self.chronos_engine = MockChronosEngineForAdapterTest(self)
            self.ethos_config = {"pathos_home_timezone": "America/New_York"}

        async def get_local_datetime_for_user(self, user_id: str) -> datetime:
            logger_main.info(f"MockEthosCore.get_local_datetime_for_user called for {user_id}")
            assert user_id == self.PATHOS_USER_ID
            tz_str = self.ethos_config.get('pathos_home_timezone', "UTC")
            tz = timezone.utc
            if ZoneInfo and tz_str.lower() != "utc":
                try: tz = ZoneInfo(tz_str)
                except Exception as e_tz: logger_main.warning(f"MockEthosCore Warning: Could not use timezone '{tz_str}': {e_tz}")
            return datetime.now(tz)

    mock_ethos_instance = MockEthosCoreForAdapterTest()

    async def main_tests():
        adapter = ChronosAdapter(ethos_core=mock_ethos_instance)

        logger_main.info("\n1. Testing get_current_block (async class method) ---")
        current_block_default = await adapter.get_current_block()
        if current_block_default:
            logger_main.info("   Current Schedule Block (via adapter):")
            for key, value in current_block_default.items(): logger_main.info(f"     {key}: {value}")
            assert current_block_default["id"] == "mock_slot_123"
            assert current_block_default["name"] == "Mocked Activity from Chronos"
        else: logger_main.error("   adapter.get_current_block() returned None or an error block.")

        logger_main.info("\n2. Testing get_current_block override (via patch):")
        with unittest.mock.patch.object(adapter, 'get_current_block', new_callable=unittest.mock.AsyncMock) as mock_method:
            mock_method.return_value = {"id": "override_test", "name": "Overridden Block", "type":"test"}
            overridden_block = await adapter.get_current_block()
            assert overridden_block["id"] == "override_test"
            logger_main.info(f"   Overridden block (via patch): {overridden_block}")

        logger_main.info("\n3. Testing get_current_block() after patch (should use actual method again):")
        current_block_after_reset = await adapter.get_current_block()
        if current_block_after_reset:
            logger_main.info("   Current Schedule Block (via adapter after reset):")
            for key, value in current_block_after_reset.items(): logger_main.info(f"     {key}: {value}")
            assert current_block_after_reset["id"] == "mock_slot_123"
        else: logger_main.info("   adapter.get_current_block() returned None or an error block after reset.")

        logger_main.info("\n--- Testing get_upcoming_blocks (class method) ---")
        upcoming = await adapter.get_upcoming_blocks(2)
        logger_main.info(f"Upcoming blocks retrieved: {len(upcoming)}")
        assert len(upcoming) <= 2
        if len(upcoming) > 0:
            first_upcoming_name = upcoming[0]["name"]
            logger_main.info(f"First upcoming block name: {first_upcoming_name}")
            assert "Tomorrow" in first_upcoming_name
        if len(upcoming) == 2:
             second_upcoming_name = upcoming[1]["name"]
             logger_main.info(f"Second upcoming block name: {second_upcoming_name}")
             assert "Tomorrow" in second_upcoming_name

        logger_main.info("\n--- Testing Schedule Update Subscription and Handling (class method) ---")
        mock_firmament_event_bus_publish = unittest.mock.MagicMock()
        original_event_bus_instance_method = EventBus.instance
        EventBus.instance = unittest.mock.MagicMock(return_value=unittest.mock.MagicMock(publish=mock_firmament_event_bus_publish))

        # Test subscription
        subscribe_success = await adapter.start_listening_to_schedule_updates()
        assert subscribe_success, "Failed to subscribe to schedule updates."
        assert adapter._handle_firmament_schedule_update in mock_ethos_instance.chronos_engine._registered_listeners

        # Test notification
        test_update_date = date(2024, 7, 4)
        test_update_user = PATHOS_USER_ID

        logger_main.info(f"Simulating call to adapter's _handle_firmament_schedule_update with date: {test_update_date}, user: {test_update_user}")
        await adapter._handle_firmament_schedule_update(test_update_date, test_update_user)

        mock_firmament_event_bus_publish.assert_called_once()
        args, _ = mock_firmament_event_bus_publish.call_args
        assert args[0] == FIRMAMENT_SCHEDULE_RELOAD_REQUESTED
        assert args[1]["affected_date"] == test_update_date.isoformat()
        assert args[1]["user_id"] == test_update_user
        logger_main.info("Schedule update handler correctly published to Firmament EventBus.")

        # Test unsubscription
        await adapter.stop_listening_to_schedule_updates()
        assert adapter._handle_firmament_schedule_update not in mock_ethos_instance.chronos_engine._registered_listeners
        logger_main.info("Adapter successfully unsubscribed.")

        EventBus.instance = original_event_bus_instance_method

        logger_main.info("\n--- Chronos Adapter testing finished ---")

    asyncio.run(main_tests())
