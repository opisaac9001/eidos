"""
Main API for the Eidos Agent.

This FastAPI application exposes various endpoints for interacting with the Eidos agent,
including hooks for receiving data from the Pathos Subconscious Node.
"""
import logging
from fastapi import FastAPI, HTTPException, APIRouter

# Attempt to import models from the subconscious module.
# This structure assumes that 'eidos_agent' is in the Python path.
try:
    from eidos_agent.modules.subconscious.models import ImpulseData, ImprintData
    from eidos_agent.modules.ferment import handle_external_impulse
    from eidos_agent.modules.memories import store_imprint
except ImportError as e:
    # This fallback is mostly for isolated testing of this file if the full structure isn't in PYTHONPATH.
    # In a proper package installation, this shouldn't be necessary.
    logging.warning(f"Could not import Eidos modules directly, attempting relative for dev: {e}")
    try:
        from ..modules.subconscious.models import ImpulseData, ImprintData
        from ..modules.ferment import handle_external_impulse
        from ..modules.memories import store_imprint
    except ImportError:
        logging.exception("Failed to import Eidos modules. Ensure eidos_agent is in PYTHONPATH or structure is correct.")
        # Define dummy models if import fails, to allow FastAPI to start but endpoints will fail
        class ImpulseData(logging.getLoggerClass()): pass # Dummy class
        class ImprintData(logging.getLoggerClass()): pass # Dummy class
        def handle_external_impulse(*args, **kwargs): raise RuntimeError("Module not loaded")
        def store_imprint(*args, **kwargs): raise RuntimeError("Module not loaded")


# --- FastAPI App Instance ---
app = FastAPI(
    title="Eidos Agent API",
    description="Main API for the Eidos intelligent agent.",
    version="0.1.0"
)

# Configure basic logging if not already configured (e.g., by Uvicorn)
# This is mainly for direct script execution or testing.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- API Router for Subconscious Hooks (Optional, but good practice) ---
# router = APIRouter() # Example if we want to use a router

# --- Subconscious Node Hooks ---

@app.post("/v1/pathos/impulse", summary="Receive impulse from Pathos subconscious node")
async def handle_subconscious_impulse(data: ImpulseData):
    """
    Endpoint to receive an impulsive thought from the Pathos subconscious node.
    This data is then passed to the Eidos agent's "ferment" module for processing.
    """
    logger.info(f"Eidos API: Received impulse from Pathos: {data.dict()}")
    try:
        # Pass data to the appropriate Eidos module (e.g., ferment)
        result = handle_external_impulse(
            thought=data.thought,
            timestamp=data.timestamp,
            mood=data.mood_snapshot
        )
        logger.info(f"Eidos API: Impulse processed by ferment module. Result: {result}")
        return result
    except Exception as e:
        logger.exception(f"Eidos API: Error processing impulse: {data.dict()}")
        raise HTTPException(status_code=500, detail=f"Error processing impulse in Eidos: {str(e)}")

@app.post("/v1/pathos/memory/imprint", summary="Receive memory imprint from Pathos subconscious node")
async def store_subconscious_memory_imprint(data: ImprintData):
    """
    Endpoint to receive a memory imprint from the Pathos subconscious node.
    This data is then passed to the Eidos agent's "memories" module for storage.
    """
    logger.info(f"Eidos API: Received memory imprint from Pathos: {data.dict()}")
    try:
        # Pass data to the appropriate Eidos module (e.g., memories)
        result = store_imprint(
            content=data.content,
            timestamp=data.timestamp,
            mood=data.mood,
            topics=data.topics
        )
        logger.info(f"Eidos API: Imprint processed by memories module. Result: {result}")
        return result
    except Exception as e:
        logger.exception(f"Eidos API: Error processing memory imprint: {data.dict()}")
        raise HTTPException(status_code=500, detail=f"Error processing imprint in Eidos: {str(e)}")

# Example: Include router if it was used
# app.include_router(router, prefix="/hooks")

@app.get("/", include_in_schema=False)
async def root():
    return {"message": "Eidos Agent API is active. See /docs for available endpoints."}

# To run this API (for testing purposes):
# Ensure FastAPI and Uvicorn are installed: pip install fastapi uvicorn
# Run from the directory containing 'eidos_agent': python -m eidos_agent.api.main
# (This assumes your project structure allows this type of execution)
# Or, more commonly: uvicorn eidos_agent.api.main:app --reload --port 8080
# (Run from the project root directory, e.g., the parent of 'eidos_agent')

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Eidos Agent API directly using Uvicorn (for development/testing)...")
    # Note: For production, use a proper ASGI server like Gunicorn with Uvicorn workers.
    # The path 'eidos_agent.api.main:app' might need adjustment based on how you run it.
    # If run as `python eidos_agent/api/main.py`, then `main:app` or `api.main:app` might be needed
    # depending on current working directory and PYTHONPATH.
    # A common way from project root: uvicorn eidos_agent.api.main:app --reload --port 8080
    uvicorn.run(app, host="0.0.0.0", port=8080)
