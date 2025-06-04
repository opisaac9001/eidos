import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional # Added Optional

from eidos_agent.features.firmament_module.module import FirmamentModule

# Global variable to hold the FirmamentModule instance for this router
_current_firmament_module: Optional[FirmamentModule] = None

def init_firmament_router(fm_module: FirmamentModule):
    '''
    Initializes the Firmament router with the FirmamentModule instance.
    This is called from main.py during startup.
    '''
    global _current_firmament_module
    _current_firmament_module = fm_module
    logger.info("Firmament router initialized with FirmamentModule instance.")

async def get_firmament_module_dependency() -> FirmamentModule:
    '''
    FastAPI dependency provider for FirmamentModule.
    '''
    if _current_firmament_module is None:
        logger.error("FirmamentModule dependency not available. Router not properly initialized from main.py.")
        raise HTTPException(
            status_code=503, # Service Unavailable
            detail="FirmamentModule is not available or not initialized for this router."
        )
    return _current_firmament_module

router = APIRouter(
    prefix="/v1/firmament",
    tags=["Firmament Engine"],
)

logger = logging.getLogger(__name__)

class SubconsciousIntentionPayload(BaseModel):
    intention: str
    metadata: Dict[str, Any] = {} # Default to empty dict if not provided

@router.post(
    "/subconscious_intention",
    summary="Receive an actionable intention from the subconscious node",
    response_model=Dict[str, str] # Using Dict for simple response
)
async def handle_subconscious_intention(
    payload: SubconsciousIntentionPayload,
    firmament_module: FirmamentModule = Depends(get_firmament_module_dependency) # Updated
):
    logger.info(
        f"Firmament Router: Received subconscious intention: '{payload.intention[:100]}...'. "
        f"Metadata keys: {list(payload.metadata.keys())}"
    )
    try:
        await firmament_module.receive_subconscious_intention(
            intention=payload.intention,
            metadata=payload.metadata
        )
        return {"message": "Subconscious intention received and queued for processing by Firmament."}
    except NotImplementedError as nie:
        logger.error(f"Firmament Router: FirmamentModule dependency not available: {nie}")
        raise HTTPException(
            status_code=501, # Not Implemented
            detail="FirmamentModule is not available due to missing dependency setup."
        )
    except Exception as e:
        logger.error(f"Firmament Router: Error processing subconscious intention: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error processing subconscious intention: {str(e)}"
        )
