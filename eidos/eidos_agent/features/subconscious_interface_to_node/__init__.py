# eidos_agent/features/subconscious_interface_to_node/__init__.py
"""
Provides the client interface and models for Eidos to communicate
with the external Pathos Subconscious Node.
"""
import logging # Added import for logger

# Re-export key elements from the client if desired, e.g.:
# from .subconscious.client import get_current_thoughts, sync_recent_context
# from .subconscious.models import ImpulseData, ImprintData
# For now, we'll let imports be more direct until usage patterns are clearer.

logger = logging.getLogger(__name__)
logger.info("eidos_agent.features.subconscious_interface_to_node package loaded.")
