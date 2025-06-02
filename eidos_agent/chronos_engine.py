"""
Handles scheduled and background tasks for the Eidos agent.

This module implements a periodic scheduler using threading.Timer to synchronize
relevant Eidos context (conversation summaries, current actions) with the
Pathos Subconscious Node.
"""
import time
import logging
import threading
from typing import Optional # For type hinting scheduler_timer

# Attempt to import from subconscious client
try:
    from eidos_agent.modules.subconscious.client import sync_recent_context
except ImportError:
    logging.warning("chronos_engine: Could not import sync_recent_context. Using placeholder for testing.")
    # Placeholder for sync_recent_context if the import fails
    def sync_recent_context(conversation: str, current_action: str) -> bool:
        print(f"Placeholder sync_recent_context called with: Conversation='{conversation[:50]}...', Action='{current_action}'")
        if not hasattr(sync_recent_context, 'call_count'):
            sync_recent_context.call_count = 0
        sync_recent_context.call_count +=1
        return sync_recent_context.call_count % 2 != 0 # Alternate true/false


# Configure basic logging
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Global Scheduler Control ---
scheduler_stop_event = threading.Event()
scheduler_timer: Optional[threading.Timer] = None

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
    """
    logger.info("ChronosEngine: Performing scheduled subconscious context sync...")
    summary = get_latest_conversation_summary()
    action = get_current_eidos_action()

    logger.debug(f"ChronosEngine: Conversation summary: '{summary}'")
    logger.debug(f"ChronosEngine: Current Eidos action: '{action}'")

    success = sync_recent_context(conversation=summary, current_action=action)

    if success:
        logger.info("ChronosEngine: Scheduled context sync with subconscious node completed successfully.")
    else:
        logger.warning("ChronosEngine: Scheduled context sync with subconscious node failed or partially failed.")

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
