"""
Handles scheduled and background tasks for the Eidos agent.

This module implements a periodic scheduler using threading.Timer to synchronize
relevant Eidos context (conversation summaries, current actions) with the
Pathos Subconscious Node.
"""
import time
import logging
import threading
from typing import Optional, TYPE_CHECKING, Any, Coroutine # Added Any, Coroutine
import asyncio
from datetime import datetime, timezone
import random
from concurrent.futures import TimeoutError # For future.result() timeout

# Attempt to import from subconscious client
# Ensure this matches the actual location of your client module
try:
    from eidos_agent.features.subconscious_interface_to_node.subconscious.client import (
        sync_recent_context,
        send_node_control_command,
        sync_mood_to_subconscious,
        inject_significant_memory_summary
    )
except ImportError as e:
    logging.critical(f"subconscious_context_scheduler: Failed to import client functions: {e}. Scheduler cannot operate.", exc_info=True)
    # Define placeholders that will raise errors or clearly indicate failure if called
    def _missing_client_func(*args, **kwargs):
        msg = "Subconscious client function not loaded due to import error."
        logger.error(msg)
        # raise NotImplementedError(msg) # Option 1: Hard fail
        return False # Option 2: Soft fail, but scheduler might not do its job

    sync_recent_context = _missing_client_func
    send_node_control_command = _missing_client_func
    sync_mood_to_subconscious = _missing_client_func
    inject_significant_memory_summary = _missing_client_func


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

# --- Initialization & Async Helper ---
def init_scheduler(ethos_core_input: 'EthosCore'):
    '''
    Initializes the scheduler with necessary module instances and captures the main event loop.
    Called from main.py during startup.
    '''
    global _ethos_core_instance, _main_event_loop
    _ethos_core_instance = ethos_core_input
    logger.info("SubconsciousContextScheduler initialized with EthosCore instance.")
    try:
        _main_event_loop = asyncio.get_running_loop()
        logger.info("Scheduler: Successfully captured main event loop.")
    except RuntimeError:
        _main_event_loop = None
        logger.warning("Scheduler: No running event loop found during init. Will use asyncio.run(), which might cause issues if Eidos has a separate main loop.")

def run_async_from_thread(coro: Coroutine[Any, Any, Any], loop_timeout: float = 10.0) -> Any:
    """
    Safely runs an async coroutine from a synchronous thread.
    Uses asyncio.run_coroutine_threadsafe if a main event loop is available,
    otherwise falls back to asyncio.run() with warnings.
    """
    global _main_event_loop
    if _main_event_loop and _main_event_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(coro, _main_event_loop)
        try:
            # Wait for the result with a timeout
            return future.result(timeout=loop_timeout)
        except TimeoutError: # from concurrent.futures.TimeoutError
            logger.error(f"Async call from thread timed out after {loop_timeout}s: {coro.__name__ if hasattr(coro, '__name__') else 'coroutine'}")
            return None
        except Exception as e:
            logger.error(f"Exception in async call from thread '{coro.__name__ if hasattr(coro, '__name__') else 'coroutine'}': {e}", exc_info=True)
            return None
    else:
        logger.warning(
            f"Scheduler: No main event loop or loop not running. Using asyncio.run() for '{coro.__name__ if hasattr(coro, '__name__') else 'coroutine'}'. "
            "This may cause errors if Eidos has a separate main event loop."
        )
        try:
            return asyncio.run(coro)
        except RuntimeError as e_run:
            if "cannot run event loop while another loop is running" in str(e_run).lower() or \
               "asyncio.run() cannot be called from a running event loop" in str(e_run).lower():
                logger.error(f"Scheduler ('{coro.__name__ if hasattr(coro, '__name__') else 'coroutine'}'): asyncio.run() conflict. Details: {e_run}")
            else:
                logger.error(f"Scheduler ('{coro.__name__ if hasattr(coro, '__name__') else 'coroutine'}'): Error running with asyncio.run(): {e_run}", exc_info=True)
            return None
        except Exception as e_generic:
            logger.error(f"Scheduler ('{coro.__name__ if hasattr(coro, '__name__') else 'coroutine'}'): Unexpected error with asyncio.run(): {e_generic}", exc_info=True)
            return None

# --- Data Retrieval Functions ---

def get_latest_conversation_summary() -> str:
    """
    Retrieves a summary of the latest conversation from EthosCore.
    """
    if not _ethos_core_instance:
        logger.warning("Scheduler (conv_summary): EthosCore instance not available.")
        return "Conversation summary: Unknown (EthosCore not available)"
    try:
        logger.debug("Scheduler (conv_summary): Attempting to retrieve recent memories.")
        coro = _ethos_core_instance.retrieve_relevant_memories(
            query_text="recent conversation snippets", # Generic query
            n_results=3,
            user_id_context="pathos_agent_internal", # TODO: Use constant
            filter_types=["user_interaction", "llm_response", "dialogue_summary"]
        )
        recent_memories = run_async_from_thread(coro)

        if recent_memories is None: # Error handled by run_async_from_thread
            return "Conversation summary: Failed to retrieve memories for summary."

        if recent_memories: # Check if list is not empty
            summary_parts = [mem.get('content', '') for mem in recent_memories]
            full_summary = " ".join(filter(None, summary_parts)).strip()
            if not full_summary:
                 return "No content in recent conversation memories."
            max_len = 500
            return (full_summary[:max_len] + '...') if len(full_summary) > max_len else full_summary
        else:
            return "No recent conversation memories found to summarize."

    except Exception as e: # Catch any other unexpected error in this synchronous part
        logger.error(f"Scheduler (conv_summary): Unexpected synchronous error: {e}", exc_info=True)
        return "Conversation summary: Failed due to unexpected synchronous error."

def get_current_eidos_action() -> str:
    """
    Retrieves Eidos agent's current action from ChronosEngine via EthosCore.
    """
    if not _ethos_core_instance or not _ethos_core_instance.chronos_engine:
        logger.warning("Scheduler (eidos_action): EthosCore or ChronosEngine instance not available.")
        return "Eidos action: Unknown (EthosCore/ChronosEngine not available)"
    try:
        logger.debug("Scheduler (eidos_action): Attempting to get current Pathos time and activity.")
        pathos_user_id = "pathos_agent_internal" # TODO: Use constant

        pathos_now_coro = _ethos_core_instance.get_local_datetime_for_user(pathos_user_id)
        pathos_now = run_async_from_thread(pathos_now_coro)

        if not pathos_now:
            logger.warning("Scheduler (eidos_action): Could not retrieve Pathos's current local time (or call failed).")
            return "Eidos action: Unknown (Could not get Pathos time)"

        activity_slot_coro = _ethos_core_instance.chronos_engine.get_current_activity(pathos_now)
        activity_slot = run_async_from_thread(activity_slot_coro)

        if activity_slot is None: # Error handled by run_async_from_thread
             return "Eidos action: Failed to retrieve current activity."

        if activity_slot: # Check if an actual slot was returned
            sub_focus_text = 'general'
            if activity_slot.activity_details and activity_slot.activity_details.sub_focus:
                sub_focus_text = activity_slot.activity_details.sub_focus
            return f"Pathos is currently: '{activity_slot.activity_title}' (Focus: {sub_focus_text})"
        else:
            return "Pathos is currently idle or between activities."

    except Exception as e: # Catch any other unexpected error in this synchronous part
        logger.error(f"Scheduler (eidos_action): Unexpected synchronous error: {e}", exc_info=True)
        return "Eidos action: Failed due to unexpected synchronous error."

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
            if _ethos_core_instance:
                logger.info("Scheduler: Attempting to generate real daily summary from EthosCore...")
                summary_coro = _ethos_core_instance.generate_daily_experiential_summary()
                summary_text = run_async_from_thread(summary_coro)

                if summary_text: # Not None and not empty
                    daily_summary = summary_text
                    logger.info("Scheduler: Successfully generated real daily summary from EthosCore.")
                elif summary_text is None: # Indicates an error from run_async_from_thread
                    logger.error("Scheduler: Failed to generate real daily summary due to async call error. Using fallback.")
                    # daily_summary remains fallback
                else: # Empty string
                    logger.warning("Scheduler: EthosCore returned empty summary, using fallback.")
                    # daily_summary remains fallback
            else:
                logger.warning("Scheduler: EthosCore instance not available. Using fallback daily summary.")

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

            # Fetch and sync actual mood from EthosCore's MoodEngine
            if _ethos_core_instance and hasattr(_ethos_core_instance, 'mood_engine') and _ethos_core_instance.mood_engine:
                # Decay mood first before getting the snapshot
                _ethos_core_instance.mood_engine.decay_mood() # Assuming decay_mood is synchronous
                logger.info("Scheduler: Applied mood decay in Eidos.")

                # get_current_mood_snapshot is synchronous in MoodEngine
                current_eidos_mood = _ethos_core_instance.mood_engine.get_current_mood_snapshot()

                if current_eidos_mood:
                    logger.info(f"Scheduler: Fetched Eidos mood for sync: {current_eidos_mood}")
                    sync_mood_success = sync_mood_to_subconscious(current_eidos_mood)
                    if sync_mood_success:
                        logger.info("Scheduler: Mood synced to subconscious node successfully.")
                    else:
                        logger.warning("Scheduler: Mood sync to subconscious node failed.")
                else:
                    logger.warning("Scheduler: Failed to fetch current Eidos mood snapshot (returned None or empty).")
            else:
                logger.warning("Scheduler: EthosCore instance or MoodEngine not available, skipping mood sync.")

            # Simulate fetching/generating significant memory summaries and inject them
            if _ethos_core_instance:
                # In a real scenario, this would involve complex logic in EthosCore.
                # For now, simulate a few plausible summaries.
                simulated_significant_memories = [
                    "Pathos recalls the satisfaction of solving a complex coding problem last week.",
                    "A fleeting memory of a childhood holiday by the sea surfaces.",
                    "The lingering feeling from a philosophical book Pathos recently finished."
                ]
                if simulated_significant_memories: # Ensure list is not empty
                    memory_to_inject = random.choice(simulated_significant_memories)
                    logger.info(f"Scheduler: Injecting simulated significant memory: {memory_to_inject}")
                    inject_success = inject_significant_memory_summary(memory_to_inject)
                    if inject_success:
                        logger.info("Scheduler: Significant memory summary injected successfully.")
                    else:
                        logger.warning("Scheduler: Failed to inject significant memory summary.")
            else:
                logger.warning("Scheduler: EthosCore instance not available, skipping significant memory injection.")
        else:
            logger.info("Scheduler: Skipping context, mood, and significant memory sync as subconscious_node is (or failed to transition from) sleeping.")

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
    # For example, let it run for (test_interval_minutes * 60 * 3.5) seconds to see about 3 executions
    run_duration_seconds = int(test_interval_minutes * 60 * 3.5) # Approx 3 cycles
    if run_duration_seconds < 1: run_duration_seconds = 1 # ensure at least 1 second sleep for very short intervals

    print(f"ChronosEngine Test: Main thread sleeping for {run_duration_seconds} seconds to observe scheduler...")

    # Loop with shorter sleeps to check stop_event more frequently if needed for other tests
    # but for this simple case, one sleep is fine.
    for _ in range(run_duration_seconds):
        if scheduler_stop_event.is_set(): # Should not be set here unless something external stops it
            break
        time.sleep(1)

    print("\nChronosEngine Test: Woke up. Requesting scheduler stop...")
    stop_subconscious_sync_scheduler()

    # Give a moment for the last timer to be properly cancelled and threads to clean up if any
    time.sleep(0.2)

    print("\n--- Testing restart behavior (should log warning if not stopped properly or start if stopped) ---")
    # Attempt to start again (if it was properly stopped, this should work)
    start_subconscious_sync_scheduler(interval_minutes=test_interval_minutes)
    time.sleep(1) # Let it run for a very short time
    stop_subconscious_sync_scheduler()


    logger.info("ChronosEngine: --- Test Run Finished ---")
