# eidos_agent/features/memories_feature/__init__.py
"""
Handles specific memory interaction features, like storing imprints
received from external sources (e.g., subconscious node).
Distinct from the core memory_storage persistence layer.
"""
import logging # Added import for logger

# Attempt to re-export key functions/classes.
# This will only work once handler.py is moved.
try:
    from .handler import store_imprint # Or other key functions
except ImportError: # pragma: no cover
    pass

logger = logging.getLogger(__name__)
logger.info("eidos_agent.features.memories_feature package loaded.")
