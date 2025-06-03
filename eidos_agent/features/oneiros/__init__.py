# eidos_agent/features/oneiros/__init__.py
"""
The Oneiros module, responsible for dream generation and related subconscious influences.
"""
import logging # Added import for logger

# Attempt to re-export key functions/classes.
# This will only work once module.py is moved.
try:
    from .module import OneirosModule
except ImportError: # pragma: no cover
    pass

logger = logging.getLogger(__name__)
logger.info("eidos_agent.features.oneiros package loaded.")
