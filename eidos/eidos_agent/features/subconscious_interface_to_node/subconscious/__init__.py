# eidos_agent/features/subconscious_interface_to_node/subconscious/__init__.py
"""
Client, models, and utilities for interacting with the Pathos Subconscious Node.
"""
import logging

# Re-export key components from this submodule
try:
    from .client import SubconsciousAPIClient # Example, adjust if class name is different
except ImportError: # pragma: no cover
    pass
try:
    from .models import ImpulseData, ImprintData # Assuming these are key models
except ImportError: # pragma: no cover
    pass

logger = logging.getLogger(__name__)
logger.info("eidos_agent.features.subconscious_interface_to_node.subconscious package loaded.")
