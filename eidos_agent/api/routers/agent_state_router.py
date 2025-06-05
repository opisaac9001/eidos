import logging
from typing import Optional, List, Dict, Any
import uuid
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from eidos_agent.schemas import (
    DreamEntryResponse,
    ApiMemoryEntry,

    MemoryEntry as GenericMemoryEntry

from pydantic import ValidationError
test
# This specific import from memory_storage might not be needed if GenericMemoryEntry from schemas is sufficient
# from eidos_agent.persona_logic.ethos_core.memory_storage import MemoryEntry # Path is already correct

from eidos_agent.persona_logic.ethos_core.core import EthosCore # Path is already correct

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/agent", tags=["Agent State"])

_ethos_core: Optional[EthosCore] = None

def init_agent_state_router(
    ethos: EthosCore
):
    global _ethos_core
    _ethos_core = ethos
    logger.info("Agent State Router initialized with Eidos EthosCore component.")

@router.get("/dreams", response_model=List[DreamEntryResponse])
async def get_agent_dreams(limit: int = 10, x_user_id: Optional[str] = Header(None, alias="X-User-Id")): # pragma: no cover
    if not _ethos_core:
        logger.error("Agent State Router: EthosCore not initialized for /dreams.")
        raise HTTPException(status_code=503, detail="Eidos system (EthosCore) not ready.")

    logger.info(f"API: Request for /v1/agent/dreams. User: {x_user_id}, Limit: {limit}")
    try:
        raw_dreams = await _ethos_core.get_recent_dreams(user_id_context=x_user_id, limit=limit)
        response_dreams: List[DreamEntryResponse] = []
        for entry in raw_dreams:
            img_url = None
            metadata = entry.get('metadata', {})
            if local_img_path_str := metadata.get('dream_image_path'):
                try:
                    img_filename = Path(local_img_path_str).name
                    img_url = f"/dream_images/{img_filename}" # Assuming a static mount at /dream_images
                except Exception as e_path: # pragma: no cover
                    logger.error(f"Error constructing image URL from dream_image_path '{local_img_path_str}': {e_path}")

            response_dreams.append(DreamEntryResponse(
                id=entry.get('id', str(uuid.uuid4())), # Fallback id
                timestamp=entry.get('timestamp', datetime.now(timezone.utc).isoformat()), # Fallback timestamp
                content=entry.get('content', '[No dream content]'),
                dream_image_url=img_url,
                dream_seed_summary=metadata.get('dream_seed_summary')
            ))
        return response_dreams
    except Exception as e: # pragma: no cover
        logger.error(f"API: Error fetching agent dreams: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error fetching agent dreams.")

@router.get("/learnings", response_model=List[ApiMemoryEntry])
async def get_agent_learnings(limit: int = 10, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    if not _ethos_core:
        logger.error("Agent State Router: EthosCore not initialized for /learnings.")
        raise HTTPException(status_code=503, detail="Eidos system (EthosCore) not ready.")

    user_id_filter = x_user_id  # Use the provided user_id directly for filtering, can be None
    logger.info(f"Request for /v1/agent/learnings. User filter: {user_id_filter}, Limit: {limit}")

    try:
        learning_types = ["learned_correction", "learned_feedback_insight", "suggestion_reflection"]
        # Assuming get_recent_learnings returns List[GenericMemoryEntry] or List[Dict]
        learnings_raw = await _ethos_core.get_recent_learnings(
            learning_types=learning_types,
            user_id_context=user_id_filter,
            limit=limit
        )

        validated_learnings: List[ApiMemoryEntry] = []
        for entry_data in learnings_raw:
            try:
                if isinstance(entry_data, dict):
                    validated_learnings.append(ApiMemoryEntry(**entry_data))
                elif hasattr(entry_data, 'model_dump'): # Pydantic v2+
                    validated_learnings.append(ApiMemoryEntry(**entry_data.model_dump()))
                elif hasattr(entry_data, 'dict'): # Pydantic v1
                    validated_learnings.append(ApiMemoryEntry(**entry_data.dict()))
                else: # pragma: no cover
                    logger.warning(f"Skipping learning entry of unexpected type: {type(entry_data)}")
            except ValidationError as e: # pragma: no cover
                logger.error(f"ApiMemoryEntry validation failed for a learning entry: {e.json(indent=2)}\nEntry data:\n{entry_data}")

        return JSONResponse(content=jsonable_encoder(validated_learnings))
    except Exception as e: # pragma: no cover
        logger.error(f"Error fetching agent learnings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error fetching agent learnings.")

@router.get("/knowledge_verifications", response_model=List[ApiMemoryEntry])
async def get_agent_knowledge_verifications(limit: int = 20, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    # x_user_id is accepted by the endpoint but not currently used by _ethos_core.get_recent_knowledge_verifications
    if not _ethos_core:
        logger.error("Agent State Router: EthosCore not initialized for /knowledge_verifications.")
        raise HTTPException(status_code=503, detail="Eidos system (EthosCore) not ready.")

    logger.info(f"Request for /v1/agent/knowledge_verifications. User: {x_user_id}, Limit: {limit}")

    try:
        if limit <= 0: # Ensure limit is positive
            limit = 20

        # Assuming get_recent_knowledge_verifications returns List[GenericMemoryEntry] or List[Dict]
        verifications_raw = await _ethos_core.get_recent_knowledge_verifications(limit=limit)

        validated_verifications: List[ApiMemoryEntry] = []
        for entry_data in verifications_raw:
            try:
                if isinstance(entry_data, dict):
                    validated_verifications.append(ApiMemoryEntry(**entry_data))
                elif hasattr(entry_data, 'model_dump'): # Pydantic v2+
                    validated_verifications.append(ApiMemoryEntry(**entry_data.model_dump()))
                elif hasattr(entry_data, 'dict'): # Pydantic v1
                    validated_verifications.append(ApiMemoryEntry(**entry_data.dict()))
                else: # pragma: no cover
                    logger.warning(f"Skipping knowledge verification entry of unexpected type: {type(entry_data)}")
            except ValidationError as e: # pragma: no cover
                logger.error(f"ApiMemoryEntry validation failed for a knowledge verification entry: {e.json(indent=2)}\nData:\n{entry_data}")

        return JSONResponse(content=jsonable_encoder(validated_verifications))
    except Exception as e: # pragma: no cover
        logger.error(f"Error fetching agent knowledge verifications: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error fetching agent knowledge verifications.")
