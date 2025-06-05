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

    if processing_interval_seconds <= 0:
        logger.error(f"OneirosProcessingTask: Invalid processing_interval_seconds ({processing_interval_seconds}s). Must be positive. Task will not run.")
        return

    logger.info(f"OneirosProcessingTask started. Check interval: {processing_interval_seconds} seconds.")

    while True:
        try:
            await asyncio.sleep(processing_interval_seconds)

            is_sleeping = subconscious_scheduler_state.get('is_subconscious_sleeping', False)
            has_fragments = oneiros_module.has_pending_fragments()


            if is_sleeping and has_fragments:
                logger.info("OneirosProcessingTask: Subconscious is sleeping and fragments pending. Starting processing.")
                try:
                    await oneiros_module.process_received_dream_fragments()
                    logger.info("OneirosProcessingTask: OneirosModule.process_received_dream_fragments() completed.")
                except Exception as e_process:
                    logger.error(f"OneirosProcessingTask: Error during OneirosModule.process_received_dream_fragments: {e_process}", exc_info=True)
            else:
                logger.debug(
                    f"OneirosProcessingTask: Conditions not met for dream processing. "
                    f"Is sleeping: {is_sleeping}, Has fragments: {has_fragments}."
                )

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
