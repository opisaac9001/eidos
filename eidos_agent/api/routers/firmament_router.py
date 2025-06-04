import logging
from fastapi import APIRouter, Depends, HTTPException # Depends & HTTPException for future endpoint
from pydantic import BaseModel
from typing import Dict, Any

# Placeholder for FirmamentModule dependency, similar to oneiros_router
from eidos_agent.features.firmament_module.module import FirmamentModule # Uncommented
async def get_firmament_module() -> FirmamentModule: # Uncommented and defined
    # This function needs to be replaced by actual dependency injection logic
    # that provides the singleton FirmamentModule instance.
    raise NotImplementedError(
        "Dependency provider 'get_firmament_module' is a placeholder and "
        "needs to be implemented to return the actual FirmamentModule instance."
    )

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
    firmament_module: FirmamentModule = Depends(get_firmament_module)
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
