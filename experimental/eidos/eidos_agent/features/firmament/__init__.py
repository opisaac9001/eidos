# eidos_agent/features/firmament/__init__.py
"""
The Firmament module, responsible for processing impulses and potentially
driving aspects of Pathos's daily life simulation and decision-making.
"""
import logging # Added import for logger

# Attempt to re-export key functions/classes.
# This will only work once handler.py is moved.
try:
    from .handler import handle_external_impulse, get_pending_impulses
except ImportError: # pragma: no cover
    pass

logger = logging.getLogger(__name__)
logger.info("eidos_agent.features.firmament package loaded.")
