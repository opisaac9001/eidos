"""
Handles scheduled and background tasks for the Eidos agent.

This module implements a periodic scheduler using threading.Timer to synchronize
relevant Eidos context (conversation summaries, current actions) with the
Pathos Subconscious Node.
"""
import time
import logging
import threading
from typing import Optional, TYPE_CHECKING # For type hinting scheduler_timer
import asyncio # For asyncio.run() and event loop management
from datetime import datetime, timezone # For time check
import random # For mood simulation

# Import client functions directly - assuming client.py is now correct and available
from eidos_agent.features.subconscious_interface_to_node.subconscious.client import (
    sync_recent_context,
    send_node_control_command,
    sync_mood_to_subconscious
)

if TYPE_CHECKING:
    from eidos_agent.persona_logic.ethos_core.core import EthosCore

# Configure basic logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Global Scheduler Control ---
scheduler_stop_event = threading.Event()
scheduler_timer: Optional[threading.Timer] = None
_ethos_core_instance: Optional['EthosCore'] = None
_main_event_loop: Optional[asyncio.AbstractEventLoop] = None

SCHEDULER_STATE = {
    'is_subconscious_sleeping': False,
    # This dictionary can be expanded later if other state needs to be shared
}

# --- Initialization ---
def init_scheduler(ethos_core_input: 'EthosCore', main_event_loop: asyncio.AbstractEventLoop):
    '''
    Initializes the scheduler with necessary module instances and the main event loop.
    Called from main.py during startup.
    '''
    global _ethos_core_instance, _main_event_loop
    _ethos_core_instance = ethos_core_input
    _main_event_loop = main_event_loop
    logger.info("SubconsciousContextScheduler initialized with EthosCore instance and main event loop.")

# --- Data Retrieval Functions ---

def get_latest_conversation_summary() -> str:
    """
    Retrieves a summary of the latest conversation from EthosCore.
    """
    if not _ethos_core_instance or not _main_event_loop:
        logger.warning("Scheduler (conv_summary): EthosCore instance or event loop not available.")
        return "Conversation summary: Unknown (EthosCore or event loop not available)"
    try:
        logger.debug("Scheduler (conv_summary): Attempting to retrieve recent memories.")
        coro = _ethos_core_instance.retrieve_relevant_memories(
                query="recent conversation snippets", # Generic query
                top_k=3,
                min_salience=0.1,
                allowed_types=["user_interaction", "llm_response", "dialogue_summary"],
                user_id_context="pathos_agent_internal" # TODO: Use constant
            )
        future = asyncio.run_coroutine_threadsafe(coro, _main_event_loop)
        recent_memories = future.result(timeout=10) # Add timeout

        if recent_memories:
            summary_parts = [mem.get('content', '') for mem in recent_memories]
            full_summary = " ".join(filter(None, summary_parts)).strip()
            if not full_summary:
                 return "No content in recent conversation memories."
            max_len = 500 # Max length for summary to send to subconscious
            return (full_summary[:max_len] + '...') if len(full_summary) > max_len else full_summary
        else:
            return "No recent conversation memories found to summarize."
    except asyncio.TimeoutError:
        logger.error("Scheduler (conv_summary): Timeout waiting for retrieve_relevant_memories.")
        return "Conversation summary: Timeout retrieving memories."
    except Exception as e: # Catch other exceptions like RuntimeError from result() if coro failed
        logger.error(f"Scheduler (conv_summary): Error retrieving memories: {e}", exc_info=True)
        return "Conversation summary: Failed to generate due to error."
    except Exception as e:
        logger.error(f"Scheduler (conv_summary): Unexpected error retrieving memories: {e}", exc_info=True)
        return "Conversation summary: Failed to generate due to unexpected error."

def get_current_eidos_action() -> str:
    """
    Retrieves Eidos agent's current action from ChronosEngine via EthosCore.
    """
    if not _ethos_core_instance or not _ethos_core_instance.chronos_engine or not _main_event_loop:
        logger.warning("Scheduler (eidos_action): EthosCore, ChronosEngine or event loop not available.")
        return "Eidos action: Unknown (Core components or event loop not available)"
    try:
        logger.debug("Scheduler (eidos_action): Attempting to get current Pathos time and activity.")
        pathos_user_id = "pathos_agent_internal" # TODO: Use constant

        # Getting local datetime for user
        coro_time = _ethos_core_instance.get_local_datetime_for_user(pathos_user_id)
        future_time = asyncio.run_coroutine_threadsafe(coro_time, _main_event_loop)
        pathos_now = future_time.result(timeout=5) # Add timeout

        if not pathos_now:
            logger.warning("Scheduler (eidos_action): Could not retrieve Pathos's current local time.")
            return "Eidos action: Unknown (Could not get Pathos time)"

        # Getting current activity
        coro_activity = _ethos_core_instance.chronos_engine.get_current_activity(pathos_now)
        future_activity = asyncio.run_coroutine_threadsafe(coro_activity, _main_event_loop)
        activity_slot = future_activity.result(timeout=5) # Add timeout

        if activity_slot:
            sub_focus_text = 'general'
            if activity_slot.activity_details and activity_slot.activity_details.sub_focus:
                sub_focus_text = activity_slot.activity_details.sub_focus
            return f"Pathos is currently: '{activity_slot.activity_title}' (Focus: {sub_focus_text})"
        else:
            return "Pathos is currently idle or between activities."
    except asyncio.TimeoutError:
        logger.error("Scheduler (eidos_action): Timeout waiting for ChronosEngine activity.")
        return "Eidos action: Timeout getting current action."
    except Exception as e: # Catch other exceptions
        logger.error(f"Scheduler (eidos_action): Error getting current action: {e}", exc_info=True)
        return "Eidos action: Failed to get due to error."

# --- Scheduled Task Implementation ---

def perform_scheduled_subconscious_context_sync():
    """
    Performs the scheduled task of synchronizing context with the subconscious node.

    Retrieves the latest conversation summary and current Eidos action, then
    sends this information to the subconscious node.
    Also handles transitioning to SLEEPING_DREAMING state at night.
    """
    logger.info("Scheduler: Performing scheduled subconscious context sync...")

    # Determine current hour (e.g., based on system time where scheduler runs, assuming UTC for now or local server time)
    # For more accuracy, this should use Pathos's local time if EthosCore is available.
    # However, EthosCore calls are async, and this function is sync.
    # A simpler time check for now:
    current_hour = datetime.now(timezone.utc).hour # Or use a configured timezone if scheduler runs in a specific one

    # Define night time, e.g., 10 PM to 6 AM
    # This could be made configurable later.
    is_night_time = 22 <= current_hour or current_hour < 6 # Define night time, e.g., 10 PM to 6 AM (UTC for now)
    # MORNING_HOUR_START could be a config, e.g. 6
    # NIGHT_HOUR_START could be a config, e.g. 22

    if is_night_time:
        if not SCHEDULER_STATE.get('is_subconscious_sleeping', False):
            logger.info("Scheduler: Night time. Attempting to transition subconscious to SLEEPING_DREAMING state.")
            daily_summary = "Pathos experienced a day of various activities and thoughts. (Fallback summary)"
            if _ethos_core_instance and _main_event_loop:
                logger.info("Scheduler: Attempting to generate real daily summary from EthosCore...")
                try:
                    logger.debug("Scheduler: Calling EthosCore.generate_daily_experiential_summary() via run_coroutine_threadsafe...")
                    coro_summary = _ethos_core_instance.generate_daily_experiential_summary()
                    future_summary = asyncio.run_coroutine_threadsafe(coro_summary, _main_event_loop)
                    summary_text = future_summary.result(timeout=30) # Longer timeout for summary generation

                    if summary_text:
                        daily_summary = summary_text
                        logger.info("Scheduler: Successfully generated real daily summary from EthosCore.")
                    else:
                        logger.warning("Scheduler: EthosCore returned empty summary, using fallback.")
                except asyncio.TimeoutError:
                    logger.error("Scheduler: Timeout generating real daily summary from EthosCore.")
                except Exception as e_sum_gen:
                    logger.error(f"Scheduler: Error during daily summary generation: {e_sum_gen}", exc_info=True)
            else:
                logger.warning("Scheduler: EthosCore instance or event loop not available. Using fallback daily summary.")

            logger.info(f"Scheduler: Sending command to transition subconscious to SLEEPING_DREAMING with summary: {daily_summary[:100]}...")
            success_sleep_command = send_node_control_command(node_state="SLEEPING_DREAMING", daily_summary=daily_summary)
            if success_sleep_command:
                logger.info("Scheduler: Command to set SLEEPING_DREAMING state sent successfully.")
                SCHEDULER_STATE['is_subconscious_sleeping'] = True
            else:
                logger.warning("Scheduler: Failed to send SLEEPING_DREAMING state command. Node may not be sleeping.")
                SCHEDULER_STATE['is_subconscious_sleeping'] = False # Explicitly not sleeping if command failed
        else:
            logger.info("Scheduler: Night time, and subconscious_node already marked as sleeping.")

    else: # Daytime
        if SCHEDULER_STATE.get('is_subconscious_sleeping', False):
            logger.info("Scheduler: Daytime. Attempting to transition subconscious to AWAKE_THINKING state.")
            success_wake_command = send_node_control_command(node_state="AWAKE_THINKING")
            if success_wake_command:
                logger.info("Scheduler: Command to set AWAKE_THINKING state sent successfully.")
                SCHEDULER_STATE['is_subconscious_sleeping'] = False
            else:
                logger.warning("Scheduler: Failed to send AWAKE_THINKING state command. Node may still be sleeping.")
                # SCHEDULER_STATE remains True here, as we failed to confirm it's awake.
        else:
            SCHEDULER_STATE['is_subconscious_sleeping'] = False
            logger.info("Scheduler: Daytime. Subconscious_node assumed or already AWAKE.")

        if not SCHEDULER_STATE.get('is_subconscious_sleeping', False):
            logger.info("Scheduler: Performing standard context sync with subconscious_node.")
            # Sync conversation and action context
            summary = get_latest_conversation_summary()
            action = get_current_eidos_action()
            logger.debug(f"Scheduler: Conversation summary for sync: '{summary}'")
            logger.debug(f"Scheduler: Current Eidos action for sync: '{action}'")
            sync_context_success = sync_recent_context(conversation=summary, current_action=action)
            if sync_context_success:
                logger.info("Scheduler: Scheduled context (conversation/action) sync with subconscious node completed successfully.")
            else:
                logger.warning("Scheduler: Scheduled context (conversation/action) sync with subconscious node failed or partially failed.")

            # Fetch Hexus scores from EthosCore and sync them
            if _ethos_core_instance: # No need for main_event_loop here as get_current_mood is sync
                try:
                    logger.debug("Scheduler: Attempting to fetch current Hexus scores from EthosCore...")
                    # EthosCore.get_current_mood() returns a dict including 'hexus_snapshot'
                    current_eidos_mood_data = _ethos_core_instance.get_current_mood()
                    hexus_snapshot_to_sync = current_eidos_mood_data.get("hexus_snapshot")

                    if hexus_snapshot_to_sync and isinstance(hexus_snapshot_to_sync, dict):
                        logger.info(f"Scheduler: Fetched Eidos Hexus snapshot for sync: {hexus_snapshot_to_sync}")
                        sync_mood_success = sync_mood_to_subconscious(hexus_snapshot_to_sync)
                        if sync_mood_success:
                            logger.info("Scheduler: Hexus snapshot synced to subconscious node successfully.")
                        else:
                            logger.warning("Scheduler: Hexus snapshot sync to subconscious node failed.")
                    elif current_eidos_mood_data.get("simulation_disabled"):
                        logger.info("Scheduler: Mood/Hexus simulation is disabled in EthosCore. Not syncing Hexus.")
                    else:
                        logger.warning("Scheduler: EthosCore.get_current_mood() did not return a valid 'hexus_snapshot'. Current data: {current_eidos_mood_data}")

                except Exception as e_mood:
                    logger.error(f"Scheduler: Error fetching or syncing Eidos Hexus scores: {e_mood}", exc_info=True)
                    # Fallback to sending a minimal simulated mood if there's an error fetching the real one
                    logger.warning("Scheduler: Using minimal simulated Hexus scores for sync due to error.")
                    simulated_hexus_fallback = { # Provide some basic Hexus scores
                        "focus": random.uniform(0.3, 0.7),
                        "curiosity": random.uniform(0.4, 0.8)
                    }
                    sync_mood_to_subconscious(simulated_hexus_fallback)
            else:
                logger.warning("Scheduler: EthosCore instance not available, skipping Hexus scores sync.")
                # Fallback to simulated mood if core components are missing
                simulated_eidos_mood = {
                    "impulsiveness": round(random.uniform(0.2, 0.8), 2),
                    "proactivity": round(random.uniform(0.3, 0.7), 2),
                }
                logger.info(f"Scheduler: Using basic simulated Eidos mood for sync: {simulated_eidos_mood}")
                sync_mood_success = sync_mood_to_subconscious(simulated_eidos_mood)
                if sync_mood_success: logger.info("Scheduler: Basic simulated mood synced to subconscious node successfully.")
                else: logger.warning("Scheduler: Basic simulated mood sync to subconscious node failed.")
        else:
            logger.info("Scheduler: Skipping context and mood sync as subconscious_node is (or failed to transition from) sleeping.")

# --- Scheduler Implementation ---

def _run_periodic_sync(interval_seconds: int):
    """
    Internal function executed periodically by the scheduler.

    If the stop event is not set, it performs the sync task and then
    schedules itself to run again.
    """
    global scheduler_timer # Allow modification of the global timer variable
    if not scheduler_stop_event.is_set():
        perform_scheduled_subconscious_context_sync()

        # Schedule the next run only if the stop event is still not set
        if not scheduler_stop_event.is_set():
            scheduler_timer = threading.Timer(interval_seconds, _run_periodic_sync, args=[interval_seconds])
            scheduler_timer.daemon = True  # Allows main program to exit even if timer is active
            scheduler_timer.start()
            logger.debug(f"ChronosEngine: Next sync scheduled in {interval_seconds} seconds.")
        else:
            logger.info("ChronosEngine: Stop event set after task execution, not scheduling next run.")
    else:
        logger.info("ChronosEngine: Stop event set, periodic sync task not executed.")


def start_subconscious_sync_scheduler(interval_minutes: float = 5.0):
    """
    Starts the periodic scheduler for subconscious context synchronization.

    The scheduler uses threading.Timer to run the sync task at approximately
    the specified interval.

    Args:
        interval_minutes: The interval in minutes at which the sync should occur.
    """
    global scheduler_timer # Allow modification of the global timer variable

    if scheduler_timer and scheduler_timer.is_alive():
        logger.warning("ChronosEngine: Scheduler already running. Please stop it before starting again.")
        return

    scheduler_stop_event.clear() # Clear the stop event in case it was set previously
    interval_seconds = interval_minutes * 60

    logger.info(f"ChronosEngine: Starting subconscious context sync scheduler. Interval: {interval_minutes} minutes.")

    # Kick off the first execution of the periodic task
    # Subsequent runs will be scheduled by _run_periodic_sync itself
    _run_periodic_sync(interval_seconds)


def stop_subconscious_sync_scheduler():
    """
    Stops the periodic subconscious context sync scheduler.

    Sets an event to signal the scheduler loop to terminate and cancels
    any active timer.
    """
    global scheduler_timer # Allow access to the global timer variable
    logger.info("ChronosEngine: Requesting stop for subconscious context sync scheduler...")
    scheduler_stop_event.set() # Signal the loop to stop

    if scheduler_timer and scheduler_timer.is_alive():
        scheduler_timer.cancel() # Attempt to cancel the currently scheduled timer
        logger.info("ChronosEngine: Active scheduler timer cancelled.")
    scheduler_timer = None # Clear the timer variable
    logger.info("ChronosEngine: Subconscious context sync scheduler stopped.")


if __name__ == '__main__':
    logger.info("ChronosEngine: --- Test Run for Periodic Scheduler ---")

    test_interval_minutes = 0.1 # 6 seconds for quick testing

    print(f"\n--- Starting scheduler with interval: {test_interval_minutes} minutes ({test_interval_minutes*60} seconds) ---")
    start_subconscious_sync_scheduler(interval_minutes=test_interval_minutes)

    # Let the scheduler run for a few cycles
    # --- Mocking for Test Run ---
    class MockEthosCore:
        def __init__(self):
            self.chronos_engine = MockChronosEngine()
            self.mood_engine = MockMoodEngine() # Added mood engine

        async def retrieve_relevant_memories(self, query, top_k, min_salience, allowed_types, user_id_context):
            print(f"MockEthosCore: retrieve_relevant_memories called with query='{query}'")
            await asyncio.sleep(0.01) # Simulate async work
            return [{"content": "Test memory 1"}, {"content": "Another conversation bit"}]

        async def get_local_datetime_for_user(self, user_id):
            print(f"MockEthosCore: get_local_datetime_for_user called for user_id='{user_id}'")
            await asyncio.sleep(0.01)
            return datetime.now(timezone.utc)

        async def generate_daily_experiential_summary(self):
            print("MockEthosCore: generate_daily_experiential_summary called")
            await asyncio.sleep(0.02) # Simulate longer work
            return "This was a mock day full of mock experiences."

    class MockChronosEngine:
        async def get_current_activity(self, pathos_now):
            print(f"MockChronosEngine: get_current_activity called for time {pathos_now}")
            await asyncio.sleep(0.01)
            # Simulate finding an activity or not
            if random.choice([True, False]):
                return MockActivitySlot("Mock Activity", "mock_focus")
            return None

    class MockMoodEngine: # Added mock mood engine
        async def get_current_mood_snapshot(self):
            print("MockMoodEngine: get_current_mood_snapshot called")
            await asyncio.sleep(0.01)
            return {"valence": random.uniform(-1,1), "arousal": random.uniform(0,1)}


    class MockActivitySlot:
        def __init__(self, title, sub_focus):
            self.activity_title = title
            self.activity_details = MockActivityDetails(sub_focus)

    class MockActivityDetails:
        def __init__(self, sub_focus):
            self.sub_focus = sub_focus
    # --- End Mocking ---

    async def main_test_loop():
        global _main_event_loop # Allow modification for test
        _main_event_loop = asyncio.get_running_loop()

        logger.info("ChronosEngine: --- Test Run for Periodic Scheduler (with Mocks) ---")
        mock_ethos = MockEthosCore()
        init_scheduler(mock_ethos, _main_event_loop) # type: ignore

        test_interval_minutes = 0.1 # 6 seconds for quick testing

        print(f"\n--- Starting scheduler with interval: {test_interval_minutes} minutes ({test_interval_minutes*60} seconds) ---")
        start_subconscious_sync_scheduler(interval_minutes=test_interval_minutes)

        run_duration_seconds = int(test_interval_minutes * 60 * 3.5)
        if run_duration_seconds < 1: run_duration_seconds = 1

        print(f"ChronosEngine Test: Main thread (async test loop) waiting for {run_duration_seconds} seconds to observe scheduler...")
        await asyncio.sleep(run_duration_seconds)

        print("\nChronosEngine Test: Woke up. Requesting scheduler stop...")
        stop_subconscious_sync_scheduler()
        await asyncio.sleep(0.2) # Give time for cleanup

        print("\n--- Testing restart behavior ---")
        start_subconscious_sync_scheduler(interval_minutes=test_interval_minutes)
        await asyncio.sleep(1)
        stop_subconscious_sync_scheduler()
        await asyncio.sleep(0.2)

        logger.info("ChronosEngine: --- Test Run Finished ---")

    # Setup for running the async main_test_loop
    # This part replaces the old if __name__ == '__main__': block
    try:
        asyncio.run(main_test_loop())
    except KeyboardInterrupt:
        logger.info("Test run interrupted by user.")
    finally:
        # Ensure scheduler is stopped if test is exited prematurely
        if scheduler_timer and scheduler_timer.is_alive():
            stop_subconscious_sync_scheduler()
            logger.info("Cleaned up scheduler on exit from test.")
