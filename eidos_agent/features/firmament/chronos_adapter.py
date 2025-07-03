import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

# Assuming ChronosEngine and ActivitySlot will be importable
# For development, if they are in a directory not yet in PYTHONPATH, this might show as an error
# but should resolve when the full package structure is recognized.
from eidos_agent.persona_logic.chronos_engine.engine import ChronosEngine
from eidos_agent.persona_logic.chronos_engine.models import ActivitySlot, PATHOS_USER_ID

# Assuming EthosCore might be needed for time conversions or context
from eidos_agent.persona_logic.ethos_core.core import EthosCore

from eidos_agent.utils.logger import get_logger

logger = get_logger(__name__)

class ChronosAdapter:
    def __init__(self, chronos_engine: ChronosEngine, ethos_core: EthosCore):
        self.chronos_engine = chronos_engine
        self.ethos_core = ethos_core
        logger.info("ChronosAdapter initialized.")

    async def get_current_block_for_firmament(self) -> Optional[Dict[str, Any]]:
        """
        Fetches Pathos's current activity from ChronosEngine and formats it
        into a dictionary structure expected by FirmamentModule.run_simulation_tick.
        """
        try:
            # Get current UTC time to pass to ChronosEngine
            current_utc_time = datetime.now(timezone.utc)

            # Get Pathos's current activity slot from ChronosEngine
            # PATHOS_USER_ID should be defined in chronos_engine.models
            current_activity_slot: Optional[ActivitySlot] = await self.chronos_engine.get_current_activity(
                current_time_utc=current_utc_time,
                user_id=PATHOS_USER_ID
            )

            if not current_activity_slot:
                logger.debug("ChronosAdapter: No current activity found for Pathos in ChronosEngine.")
                # Firmament might expect a default "idle" or "free_time" block.
                # For now, returning None means Firmament's simulator needs to handle this.
                return {
                    "activity_type": "IDLE", # Or "FREE_TIME"
                    "location_hint": "PathosHomeLivingRoom", # Default location
                    "duration_minutes": 30, # Default duration for an idle block
                    "description": "Pathos is currently idle or between scheduled activities.",
                    "activity_title": "Idle Time",
                    "activity_id": "default_idle_block"
                }

            # Format the ActivitySlot into the dictionary structure Firmament expects
            # This structure needs to align with what Firmament's simulator.py will use.

            # Calculate duration in minutes
            # Ensure start_time and end_time are timezone-aware (ChronosEngine should ensure this)
            duration_timedelta = current_activity_slot.end_time - current_activity_slot.start_time
            duration_minutes = int(duration_timedelta.total_seconds() / 60)

            # Extract details, providing defaults if None
            details = current_activity_slot.activity_details
            description = details.description if details else "No specific description."
            location_hint = details.location_hint if details else "PathosHome" # Default location hint
            activity_theme = details.activity_theme if details else None

            # Firmament block structure (example, adjust as needed by FirmamentModule)
            firmament_block = {
                "activity_id": current_activity_slot.id,
                "activity_title": current_activity_slot.activity_title,
                "activity_type": current_activity_slot.activity_type.value, # Get enum value
                "start_time_iso": current_activity_slot.start_time.isoformat(),
                "end_time_iso": current_activity_slot.end_time.isoformat(),
                "duration_minutes": duration_minutes,
                "description": description,
                "location_hint": location_hint,
                "activity_theme": activity_theme, # Optional
                "specific_npc_hints": details.specific_npc_hints if details else None, # Optional
                "planned_sites_or_tasks": details.planned_sites_or_tasks if details else None # Optional
            }

            logger.info(f"ChronosAdapter: Current Firmament block for Pathos: {current_activity_slot.activity_title} ({current_activity_slot.activity_type.value}) at {location_hint}")
            return firmament_block

        except Exception as e:
            logger.error(f"ChronosAdapter: Error getting current block for Firmament: {e}", exc_info=True)
            # Fallback or error representation for Firmament
            return {
                "activity_type": "ERROR_STATE",
                "location_hint": "PathosSystemSpace",
                "duration_minutes": 5,
                "description": f"Error retrieving schedule: {str(e)}",
                "activity_title": "Schedule Error",
                "activity_id": "error_schedule_block"
            }

if __name__ == '__main__':
    # Example of how ChronosAdapter might be used (requires running async context)
    # This is conceptual and needs proper mocking of ChronosEngine and EthosCore for a real test.

    class MockChronosEngine:
        async def get_current_activity(self, current_time_utc: datetime, user_id: str) -> Optional[ActivitySlot]:
            if user_id == PATHOS_USER_ID:
                # Simulate finding an activity
                if 10 <= current_time_utc.hour < 12: # Example: current activity between 10 AM and 12 PM UTC
                    return ActivitySlot(
                        id="test_activity_123",
                        user_id=PATHOS_USER_ID,
                        activity_title="Test Work Block",
                        activity_type=ActivityType.WORK,
                        start_time=current_time_utc.replace(hour=10, minute=0, second=0, microsecond=0),
                        end_time=current_time_utc.replace(hour=12, minute=0, second=0, microsecond=0),
                        activity_details=ActivityDetails(description="Working on ChronosAdapter test", location_hint="PathosOffice")
                    )
            return None

    class MockEthosCore:
        pass # EthosCore might not be directly used by the adapter's core logic if timezones are handled by ChronosEngine

    async def test_adapter():
        logger_test = get_logger("chronos_adapter_test")
        logging.basicConfig(level=logging.INFO) # Ensure logs are visible

        mock_ce = MockChronosEngine()
        mock_ec = MockEthosCore() # type: ignore

        adapter = ChronosAdapter(chronos_engine=mock_ce, ethos_core=mock_ec) # type: ignore

        logger_test.info("Testing ChronosAdapter...")

        # Test when an activity is found
        # Simulate a time when an activity should be active
        time_with_activity = datetime.now(timezone.utc).replace(hour=11, minute=0)
        # To make get_current_activity work with this time, the mock needs to be aware of it,
        # or we adjust the mock's conditions. Here, the mock is hardcoded for 10-12 UTC.

        current_block = await adapter.get_current_block_for_firmament() # Uses current time

        if current_block and current_block["activity_type"] != "ERROR_STATE":
            logger_test.info(f"Current block for Firmament (activity found scenario): {current_block}")
            assert current_block["activity_title"] == "Test Work Block"
            assert current_block["activity_type"] == ActivityType.WORK.value
            assert current_block["location_hint"] == "PathosOffice"
        elif current_block and current_block["activity_type"] == "IDLE":
            logger_test.info(f"Current block for Firmament (idle scenario): {current_block}")
        else:
            logger_test.warning(f"Test failed or error block returned: {current_block}")


        # Test when no activity is found (e.g., different time)
        # This requires a way to change the "current_time_utc" used by get_current_block_for_firmament
        # or by mocking datetime.now(timezone.utc) if it were directly used.
        # For this simple test, we rely on the mock's fixed time window.
        # If current time is outside 10-12 UTC, it should return IDLE.

        # To properly test the "no activity" path, one might need to mock datetime.now()
        # or pass the time explicitly to get_current_block_for_firmament (which it doesn't take).
        # For now, this test is illustrative.

        logger_test.info("ChronosAdapter test finished.")

    if __name__ == "__main__":
        import asyncio
        asyncio.run(test_adapter())
