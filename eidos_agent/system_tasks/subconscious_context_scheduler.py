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

# Attempt to import from subconscious client
try:
    from eidos_agent.features.subconscious_interface_to_node.subconscious.client import sync_recent_context, send_node_control_command # Updated import
except ImportError:
    logging.warning("subconscious_context_scheduler: Could not import sync_recent_context or send_node_control_command. Using placeholders for testing.")
    # Placeholder for sync_recent_context if the import fails
    def sync_recent_context(conversation: str, current_action: str) -> bool:
        print(f"Placeholder sync_recent_context called with: Conversation='{conversation[:50]}...', Action='{current_action}'")
        if not hasattr(sync_recent_context, 'call_count'):
            sync_recent_context.call_count = 0
        sync_recent_context.call_count +=1
        return sync_recent_context.call_count % 2 != 0 # Alternate true/false

    def send_node_control_command(node_state: str, daily_summary: Optional[str] = None) -> bool:
        print(f"Placeholder send_node_control_command called with: NodeState='{node_state}', Summary='{daily_summary[:50] if daily_summary else None}...'")
        if not hasattr(send_node_control_command, 'call_count'):
            send_node_control_command.call_count = 0
        send_node_control_command.call_count +=1
        return send_node_control_command.call_count % 2 != 0


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

# --- Initialization ---
def init_scheduler(ethos_core_input: 'EthosCore'):
    '''
    Initializes the scheduler with necessary module instances.
    Called from main.py during startup.
    '''
    global _ethos_core_instance
    _ethos_core_instance = ethos_core_input
    logger.info("SubconsciousContextScheduler initialized with EthosCore instance.")

# --- Placeholder Data Retrieval Functions ---

def get_latest_conversation_summary() -> str:
    """
    Placeholder function to retrieve a summary of the latest conversation.
    """
    return "Placeholder conversation summary: User asked about weather, Eidos provided forecast."

def get_current_eidos_action() -> str:
    """
    Placeholder function to retrieve the Eidos agent's current action.
    """
    return "Placeholder Eidos action: 'processing_user_feedback_on_prior_turn'"

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
    is_night_time = 22 <= current_hour or current_hour < 6

    if is_night_time:
        logger.info("Scheduler: Night time detected. Preparing for dream state.")
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
        success = send_node_control_command(node_state="SLEEPING_DREAMING", daily_summary=daily_summary)
        if success:
            logger.info("Scheduler: Command to set SLEEPING_DREAMING state sent successfully.")
        else:
            logger.warning("Scheduler: Failed to send SLEEPING_DREAMING state command to subconscious node.")
    else:
        logger.info("Scheduler: Daytime detected. Performing standard context sync.")
        summary = get_latest_conversation_summary()
        action = get_current_eidos_action()

        logger.debug(f"Scheduler: Conversation summary: '{summary}'")
        logger.debug(f"Scheduler: Current Eidos action: '{action}'")

        success = sync_recent_context(conversation=summary, current_action=action)

        if success:
            logger.info("Scheduler: Scheduled context sync with subconscious node completed successfully.")
        else:
            logger.warning("Scheduler: Scheduled context sync with subconscious node failed or partially failed.")

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
