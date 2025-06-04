import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .module import FirmamentModule # Relative import for type checking

logger = logging.getLogger(__name__)

async def firmament_ticker_task(fm_module: 'FirmamentModule'):
    '''
    Periodically calls the FirmamentModule's run_simulation_tick method.
    This task is intended to be started by the main application (e.g., in main.py's lifespan).
    '''
    if not fm_module.fm_config.get("enable_firmament", False):
        logger.info("Firmament ticker task: FirmamentModule is disabled. Task will not run.")
        return

    tick_interval = fm_module.fm_config.get("simulation_tick_interval_seconds", 900.0) # Default 15 mins
    if tick_interval <= 0:
        logger.error(f"Firmament ticker task: Invalid tick_interval ({tick_interval}s). Must be positive. Task will not run.")
        return

    logger.info(f"Firmament ticker task started. Tick interval: {tick_interval} seconds.")

    while True:
        try:
            logger.debug("Firmament ticker task: Calling run_simulation_tick().")
            await fm_module.run_simulation_tick()
            logger.debug("Firmament ticker task: run_simulation_tick() completed.")
        except Exception as e:
            # Catching general exceptions to ensure the ticker itself doesn't die.
            # Specific errors within run_simulation_tick should be handled there.
            logger.error(f"Firmament ticker task: Unhandled error during run_simulation_tick: {e}", exc_info=True)

        try:
            await asyncio.sleep(tick_interval)
        except asyncio.CancelledError:
            logger.info("Firmament ticker task: Sleep cancelled. Task is shutting down.")
            break # Exit the loop if the sleep is cancelled (e.g., during app shutdown)
        except Exception as e:
            logger.error(f"Firmament ticker task: Error during sleep: {e}. Will attempt to continue.", exc_info=True)
            # Potentially add a shorter sleep here before retrying the loop if sleep itself errors
            # but this is highly unlikely unless there are system-level asyncio issues.
