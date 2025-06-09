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
import asyncio # For asyncio.run()
from datetime import datetime, timezone # For time check
import random # For mood simulation

# Attempt to import from subconscious client
try:
    from eidos_agent.features.subconscious_interface_to_node.subconscious.client import sync_recent_context, send_node_control_command, sync_mood_to_subconscious
except ImportError:
    logging.warning("subconscious_context_scheduler: Could not import client functions. Using placeholders for testing.")
    # Placeholder functions if the import fails
    def sync_recent_context(conversation: str, current_action: str) -> bool:
        print(f"Placeholder sync_recent_context: Conv='{conversation[:50]}...', Action='{current_action}'")
        return True

    def send_node_control_command(node_state: str, daily_summary: Optional[str] = None) -> bool:
        print(f"Placeholder send_node_control_command: State='{node_state}', Summary='{daily_summary[:50] if daily_summary else 'N/A'}'")
        return True

    def sync_mood_to_subconscious(mood_snapshot: dict) -> bool:
        print(f"Placeholder sync_mood_to_subconscious: Mood='{mood_snapshot}'")
        return True


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

SCHEDULER_STATE = {
    'is_subconscious_sleeping': False,
    # This dictionary can be expanded later if other state needs to be shared
}

# --- Initialization ---
def init_scheduler(ethos_core_input: 'EthosCore'):
    '''
    Initializes the scheduler with necessary module instances.
    Called from main.py during startup.
    '''
    global _ethos_core_instance
    _ethos_core_instance = ethos_core_input
    logger.info("SubconsciousContextScheduler initialized with EthosCore instance.")

# --- Data Retrieval Functions ---

def get_latest_conversation_summary() -> str:
    """
    Retrieves a summary of the latest conversation from EthosCore.
    """
    if not _ethos_core_instance:
        logger.warning("Scheduler (conv_summary): EthosCore instance not available.")
        return "Conversation summary: Unknown (EthosCore not available)"
    try:
        # This call needs to happen in a running event loop or be handled carefully
        # if this scheduler is in a separate thread.
        logger.debug("Scheduler (conv_summary): Attempting to retrieve recent memories.")
        recent_memories = asyncio.run(
            _ethos_core_instance.retrieve_relevant_memories(
                query_text="recent conversation snippets", # Generic query
                n_results=3,
                user_id_context="pathos_agent_internal", # TODO: Use constant
                filter_types=["user_interaction", "llm_response", "dialogue_summary"]
            )
        )
        if recent_memories:
            summary_parts = [mem.get('content', '') for mem in recent_memories]
            # Assuming memories are returned newest first, might want to reverse for chronological summary
            # summary_parts.reverse()
            full_summary = " ".join(filter(None, summary_parts)).strip()
            if not full_summary:
                 return "No content in recent conversation memories."
            max_len = 500 # Max length for summary to send to subconscious
            return (full_summary[:max_len] + '...') if len(full_summary) > max_len else full_summary
        else:
            return "No recent conversation memories found to summarize."
    except RuntimeError as e_run:
        if "cannot run event loop while another loop is running" in str(e_run).lower() or \
           "asyncio.run() cannot be called from a running event loop" in str(e_run).lower():
            logger.error(f"Scheduler (conv_summary): asyncio.run() conflict. Details: {e_run}")
            return "Conversation summary: Error due to asyncio conflict."
        else:
            logger.error(f"Scheduler (conv_summary): Runtime error retrieving memories: {e_run}", exc_info=True)
            return "Conversation summary: Error retrieving memories."
    except Exception as e:
        logger.error(f"Scheduler (conv_summary): Unexpected error retrieving memories: {e}", exc_info=True)
        return "Conversation summary: Failed to generate due to unexpected error."

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

        # Getting local datetime for user
        pathos_now = asyncio.run(_ethos_core_instance.get_local_datetime_for_user(pathos_user_id))
        if not pathos_now:
            logger.warning("Scheduler (eidos_action): Could not retrieve Pathos's current local time.")
            return "Eidos action: Unknown (Could not get Pathos time)"

        # Getting current activity
        activity_slot = asyncio.run(_ethos_core_instance.chronos_engine.get_current_activity(pathos_now))

        if activity_slot:
            sub_focus_text = 'general'
            if activity_slot.activity_details and activity_slot.activity_details.sub_focus:
                sub_focus_text = activity_slot.activity_details.sub_focus
            return f"Pathos is currently: '{activity_slot.activity_title}' (Focus: {sub_focus_text})"
        else:
            return "Pathos is currently idle or between activities."

    except RuntimeError as e_run:
        if "cannot run event loop while another loop is running" in str(e_run).lower() or \
           "asyncio.run() cannot be called from a running event loop" in str(e_run).lower():
            logger.error(f"Scheduler (eidos_action): asyncio.run() conflict. Details: {e_run}")
            return "Eidos action: Error due to asyncio conflict."
        else:
            logger.error(f"Scheduler (eidos_action): Runtime error getting current action: {e_run}", exc_info=True)
            return "Eidos action: Error getting current action."
    except Exception as e:
        logger.error(f"Scheduler (eidos_action): Unexpected error getting current action: {e}", exc_info=True)
        return "Eidos action: Failed to get due to unexpected error."

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
                try:
                    logger.debug("Scheduler: Calling asyncio.run(EthosCore.generate_daily_experiential_summary())...")
                    summary_text = asyncio.run(_ethos_core_instance.generate_daily_experiential_summary())
                    if summary_text:
                        daily_summary = summary_text
                        logger.info("Scheduler: Successfully generated real daily summary from EthosCore.")
                    else:
                        logger.warning("Scheduler: EthosCore returned empty summary, using fallback.")
                except RuntimeError as e_run:
                    if "cannot run event loop while another loop is running" in str(e_run).lower() or \
                       "asyncio.run() cannot be called from a running event loop" in str(e_run).lower():
                        logger.error(f"Scheduler: asyncio.run() conflict. Cannot generate real daily summary from sync thread. Error: {e_run}")
                        logger.error("Scheduler: THIS IS A KNOWN ISSUE. Consider refactoring scheduler to be async or use loop.call_soon_threadsafe if main loop is accessible.")
                    else:
                        logger.error(f"Scheduler: Error generating real daily summary: {e_run}", exc_info=True)
                except Exception as e_sum_gen:
                    logger.error(f"Scheduler: Unexpected error during daily summary generation: {e_sum_gen}", exc_info=True)
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

            # Simulate fetching mood from EthosCore and sync it
            if _ethos_core_instance:
                # In a real scenario, this would be:
                # current_eidos_mood = asyncio.run(_ethos_core_instance.mood_engine.get_current_mood_snapshot())
                # For now, simulate:
                simulated_eidos_mood = {
                    "impulsiveness": round(random.uniform(0.2, 0.8), 2),
                    "proactivity": round(random.uniform(0.3, 0.7), 2),
                    "valence": round(random.uniform(-0.5, 0.5), 2), # Example additional mood aspect
                    "focus": round(random.uniform(0.1, 0.9), 2) # Another example
                }
                logger.info(f"Scheduler: Simulated Eidos mood for sync: {simulated_eidos_mood}")
                sync_mood_success = sync_mood_to_subconscious(simulated_eidos_mood)
                if sync_mood_success:
                    logger.info("Scheduler: Mood synced to subconscious node successfully.")
                else:
                    logger.warning("Scheduler: Mood sync to subconscious node failed.")
            else:
                logger.warning("Scheduler: EthosCore instance not available, skipping mood sync.")
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
