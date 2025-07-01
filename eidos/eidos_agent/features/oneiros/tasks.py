import asyncio
import logging
from typing import TYPE_CHECKING, Dict, Any # Added Dict, Any

if TYPE_CHECKING:
    from .module import OneirosModule # Relative import for type checking

logger = logging.getLogger(__name__)

async def oneiros_processing_task(
        oneiros_module: 'OneirosModule',
        subconscious_scheduler_state: Dict[str, Any],
        processing_interval_seconds: int = 30 * 60 # Default 30 minutes
    ):
    '''
    Periodically checks if subconscious_node is sleeping and if there are pending
    dream fragments in OneirosModule, then triggers processing.
    '''
    # Check if Oneiros is enabled via the main config passed to the module
    if not oneiros_module.config.ENABLE_ONEIROS:
        logger.info("OneirosProcessingTask: OneirosModule is disabled in main config. Task will not run.")
        return

    # processing_interval_seconds is now used as the check frequency for _is_time_to_dream
    # It's distinct from dream frequency itself, which is managed within _is_time_to_dream
    if processing_interval_seconds <= 0:
        logger.warning(f"OneirosProcessingTask: Invalid processing_interval_seconds ({processing_interval_seconds}s). Using default 60s.")
        check_interval_seconds = 60.0
    else:
        check_interval_seconds = float(processing_interval_seconds)


    logger.info(f"Oneiros Dream Scheduling Task started. Check interval: {check_interval_seconds} seconds.")

    while True:
        try:
            await asyncio.sleep(check_interval_seconds)

            if not oneiros_module.ethos_core:
                logger.error("OneirosProcessingTask: EthosCore not available in OneirosModule. Cannot determine Pathos local time.")
                continue

            # Get current Pathos local time
            # Assuming PATHOS_USER_ID is accessible or defined appropriately for EthosCore context
            # If PATHOS_USER_ID needs to be imported here:
            # from eidos_agent.persona_logic.chronos_engine.engine import PATHOS_USER_ID
            current_pathos_local_time = await oneiros_module.ethos_core.get_local_datetime_for_user("pathos_agent_internal") # Use a constant or config for user ID

            if oneiros_module._is_time_to_dream(current_pathos_local_time):
                logger.info("OneirosProcessingTask: Conditions met for generating a dream.")
                try:
                    await oneiros_module.run_dream_cycle()
                    logger.info("OneirosProcessingTask: OneirosModule.run_dream_cycle() completed.")
                except Exception as e_dream_cycle:
                    logger.error(f"OneirosProcessingTask: Error during OneirosModule.run_dream_cycle: {e_dream_cycle}", exc_info=True)
            else:
                logger.debug("OneirosProcessingTask: Conditions not met for generating a dream in this cycle.")

            # Logic for processing received fragments (if any) can remain separate or be integrated
            # For now, keeping it separate as per subtask focus on time-based scheduling.
            if subconscious_scheduler_state.get('is_subconscious_sleeping', False) and oneiros_module.has_pending_fragments():
                logger.info("OneirosProcessingTask: Subconscious is sleeping and fragments pending. Starting fragment processing.")
                try:
                    await oneiros_module.process_received_dream_fragments()
                    logger.info("OneirosProcessingTask: OneirosModule.process_received_dream_fragments() completed.")
                except Exception as e_process_frag:
                    logger.error(f"OneirosProcessingTask: Error during OneirosModule.process_received_dream_fragments: {e_process_frag}", exc_info=True)

        except asyncio.CancelledError:
            logger.info("OneirosProcessingTask: Task cancelled. Shutting down.")
            break
        except Exception as e:
            logger.error(f"OneirosProcessingTask: Unhandled error in main loop: {e}. Will attempt to continue after interval.", exc_info=True)
            # If sleep itself errors, this might loop fast. Adding a small failsafe sleep.
            if not isinstance(e, asyncio.CancelledError): # Avoid sleeping if it was a cancellation
                try:
                    await asyncio.sleep(5) # Failsafe short sleep
                except asyncio.CancelledError:
                    logger.info("OneirosProcessingTask: Failsafe sleep cancelled during shutdown.")
                    break
