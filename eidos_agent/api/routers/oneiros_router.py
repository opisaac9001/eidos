import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List

from eidos_agent.features.oneiros.module import OneirosModule

# This is a placeholder for the actual dependency injection setup.
# In a real setup, the main FastAPI application (e.g., in main.py)
# would provide the OneirosModule instance, possibly through a dependency provider function.
async def get_oneiros_module() -> OneirosModule:
    # This function needs to be replaced by actual dependency injection logic
    # that provides the singleton OneirosModule instance.
    # Example (if main.py has a global 'oneiros_module_instance'):
    # from eidos_agent.main import oneiros_module_instance
    # return oneiros_module_instance
    # For now, this will cause an error if not properly set up.
    raise NotImplementedError(
        "Dependency provider 'get_oneiros_module' is a placeholder and "
        "needs to be implemented to return the actual OneirosModule instance."
    )

router = APIRouter(
    prefix="/v1/oneiros",
    tags=["Oneiros Engine"],
)

logger = logging.getLogger(__name__)

class DreamFragmentPayload(BaseModel):
    fragment: str

@router.post("/dream_fragment", summary="Receive a dream fragment from the subconscious node")
async def receive_dream_fragment_from_node(
    payload: DreamFragmentPayload,
    oneiros_module: OneirosModule = Depends(get_oneiros_module)
):
    logger.info(f"Oneiros Router: Received dream fragment: '{payload.fragment[:100]}...'")
    try:
        # Assuming add_dream_fragment is an async method
        await oneiros_module.add_dream_fragment(payload.fragment)
        return {"message": "Dream fragment received successfully."}
    except NotImplementedError as nie:
        logger.error(f"Oneiros Router: Failed to get OneirosModule via placeholder: {nie}")
        raise HTTPException(status_code=501, detail="OneirosModule dependency not implemented.")
    except Exception as e:
        logger.error(f"Oneiros Router: Error processing dream fragment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing dream fragment: {str(e)}")
