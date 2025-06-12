# eidos_agent/features/simulation/__init__.py
"""
The Simulation module, responsible for NPC (Non-Player Character)
interaction simulations.
"""
import logging # Added import for logger

# Attempt to re-export key functions/classes.
# This will only work once module.py is moved.
try:
    from .module import initiate_simulated_interaction, send_message_to_simulated_npc, end_simulated_interaction
except ImportError: # pragma: no cover
    pass

logger = logging.getLogger(__name__)
logger.info("eidos_agent.features.simulation package loaded.")
