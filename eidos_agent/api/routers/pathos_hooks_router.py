"""
API Router for Eidos Agent hooks related to the Pathos Subconscious Node.

This module defines API routes using FastAPI's APIRouter for handling
interactions with the Pathos Subconscious Node, such as receiving impulses
and memory imprints. This router is intended to be included in a main
FastAPI application.
"""
import logging
from fastapi import APIRouter, HTTPException # Changed FastAPI to APIRouter

# Attempt to import models from the subconscious module.
# This structure assumes that 'eidos_agent' is in the Python path.
try:
    from eidos_agent.features.subconscious_interface_to_node.subconscious.models import ImpulseData, ImprintData # Updated import
    from eidos_agent.features.firmament import handle_external_impulse # Updated import
    from eidos_agent.features.memories_feature import store_imprint # Updated import
except ImportError as e:
    # This fallback is mostly for isolated testing of this file if the full structure isn't in PYTHONPATH.
    # In a proper package installation, this shouldn't be necessary.
    logging.warning(f"Could not import Eidos modules directly, attempting relative for dev: {e}")
    try:
        from ...features.subconscious_interface_to_node.subconscious.models import ImpulseData, ImprintData # Updated relative import
        from ...features.firmament import handle_external_impulse # Updated relative import
        from ...features.memories_feature import store_imprint # Updated relative import
    except ImportError:
        logging.exception("Failed to import Eidos modules. Ensure eidos_agent is in PYTHONPATH or structure is correct.")
        # Define dummy models if import fails, to allow FastAPI to start but endpoints will fail
        class ImpulseData(logging.getLoggerClass()): pass # Dummy class
        class ImprintData(logging.getLoggerClass()): pass # Dummy class
        def handle_external_impulse(*args, **kwargs): raise RuntimeError("Module not loaded")
        def store_imprint(*args, **kwargs): raise RuntimeError("Module not loaded")


# --- APIRouter Instance ---
router = APIRouter(
    prefix="/v1/pathos", # Optional: define a prefix for all routes in this router
    tags=["Pathos Subconscious Hooks"], # Optional: add tags for OpenAPI docs
)

# Configure basic logging if not already configured (e.g., by Uvicorn)
# This is mainly for direct script execution or testing.
# In a larger app, logging is usually configured at the application entry point.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# --- Subconscious Node Hooks ---

@router.post("/impulse", summary="Receive impulse from Pathos subconscious node")
async def handle_subconscious_impulse(data: ImpulseData):
    """
    Endpoint to receive an impulsive thought from the Pathos subconscious node.
    This data is then passed to the Eidos agent's "firmament" module for processing.
    """
    logger.info(f"Eidos API (Router): Received impulse from Pathos: {data.dict()}")
    try:
        # Pass data to the appropriate Eidos module (e.g., firmament)
        result = handle_external_impulse(
            thought=data.thought,
            timestamp=data.timestamp,
            mood=data.mood_snapshot
        )
        logger.info(f"Eidos API (Router): Impulse processed by firmament module. Result: {result}")
        return result
    except Exception as e:
        logger.exception(f"Eidos API (Router): Error processing impulse: {data.dict()}")
        raise HTTPException(status_code=500, detail=f"Error processing impulse in Eidos: {str(e)}")

@router.post("/memory/imprint", summary="Receive memory imprint from Pathos subconscious node")
async def store_subconscious_memory_imprint(data: ImprintData):
    """
    Endpoint to receive a memory imprint from the Pathos subconscious node.
    This data is then passed to the Eidos agent's "memories" module for storage.
    """
    logger.info(f"Eidos API (Router): Received memory imprint from Pathos: {data.dict()}")
    try:
        # Pass data to the appropriate Eidos module (e.g., memories)
        result = store_imprint(
            content=data.content,
            timestamp=data.timestamp,
            mood=data.mood,
            topics=data.topics
        )
        logger.info(f"Eidos API (Router): Imprint processed by memories module. Result: {result}")
        return result
    except Exception as e:
        logger.exception(f"Eidos API (Router): Error processing memory imprint: {data.dict()}")
        raise HTTPException(status_code=500, detail=f"Error processing imprint in Eidos: {str(e)}")

# Note: The root path "/" previously defined with @app.get("/") would typically not be part of a
# specific sub-router like this one, or if it is, its path would be relative to the router's prefix.
# For example, if this router is included with prefix "/pathos_hooks", then a "@router.get("/")"
# here would be accessible at "/pathos_hooks/".
# I'll remove the root GET for this router as it's specific to Pathos hooks.
# If a general API root is needed, it should be on the main FastAPI app instance.

# The file is no longer runnable as a standalone FastAPI application using uvicorn directly on this file.
# It needs to be included in a main FastAPI application.
# Example (in a different file, e.g., main_app.py):
# from fastapi import FastAPI
# from eidos_agent.api import main as pathos_hooks_router # Assuming this file is eidos_agent/api/main.py
#
# app = FastAPI()
# app.include_router(pathos_hooks_router.router) # Include the router
#
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8080)
