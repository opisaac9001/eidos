import logging
import uuid # For request_id in update_user_settings
import json # For json.loads in update_user_settings
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Header
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

# Pydantic models from eidos_agent.schemas
from eidos_agent.schemas.user_profile_schemas import UserSettingsRequest
from eidos_agent.schemas.ethos_schemas import ApiMemoryEntry, Memory as MemoryEntry
from pydantic import ValidationError

# Core Eidos components (to be injected)
from eidos_agent.persona_logic.logos_core.handler import LogosCore # Updated import
from eidos_agent.persona_logic.ethos_core.core import EthosCore # Path is already correct


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/user", tags=["User Profile"])

# Module-level globals for dependencies
_logos_core: Optional[LogosCore] = None
_ethos_core: Optional[EthosCore] = None

def init_user_profile_router(
    logos: LogosCore,
    ethos: EthosCore
):
    """Initializes the User Profile router with necessary Eidos core components."""
    global _logos_core, _ethos_core

    _logos_core = logos
    _ethos_core = ethos

    logger.info("User Profile Router initialized with Eidos core components.")

@router.post("/settings", status_code=200)
async def update_user_settings(settings_request: UserSettingsRequest, x_user_id_header: Optional[str] = Header(None, alias="X-User-Id")): # pragma: no cover
    request_id = str(uuid.uuid4())
    # Determine effective user_id, prioritizing payload, then header, then fallback
    raw_user_id_from_payload = settings_request.user_id
    raw_user_id_from_header = x_user_id_header

    effective_raw_user_id: Optional[str] = raw_user_id_from_payload
    if not effective_raw_user_id and raw_user_id_from_header:
        effective_raw_user_id = raw_user_id_from_header
    if not effective_raw_user_id: # Fallback if neither is provided
        effective_raw_user_id = "api_guest_user"

    # Normalize user_id for storage
    user_id_for_storage: str = "api_guest_user" # Default if normalization fails or input is empty
    if effective_raw_user_id and isinstance(effective_raw_user_id, str):
        normalized = effective_raw_user_id.lower().strip().replace(" ", "_")
        if normalized: # Ensure not empty after normalization
            user_id_for_storage = normalized

    logger.info(f"Request {request_id}: /v1/user/settings for user (normalized for storage) '{user_id_for_storage}'. Raw payload ID: '{raw_user_id_from_payload}', Header ID: '{raw_user_id_from_header}'.")

    if not _ethos_core or not _logos_core:
        logger.error("User Profile Router: EthosCore or LogosCore not initialized.")
        raise HTTPException(status_code=503, detail="Eidos system (core user profile components) not ready.")

    results = []
    all_ok = True
    for item in settings_request.settings:
        try:
            fact_result_str = await _logos_core.execute_store_user_fact(
                attribute_name=item.attribute_name,
                attribute_value=str(item.attribute_value),
                user_statement_context=item.user_statement_context or f"User set {item.attribute_name} via GUI settings.",
                user_id=user_id_for_storage
            )
            fact_res = json.loads(fact_result_str) # Assuming execute_store_user_fact returns a JSON string
            if fact_res.get("status") == "success":
                results.append({"attribute_name": item.attribute_name, "status": "success", "message": fact_res.get("message")})
            else:
                all_ok = False
                results.append({"attribute_name": item.attribute_name, "status": "failed", "message": fact_res.get("error")})
                logger.warning(f"Failed to store setting '{item.attribute_name}' for user '{user_id_for_storage}': {fact_res.get('error')}")
        except Exception as e:
            all_ok = False
            error_msg = f"Error processing setting '{item.attribute_name}': {str(e)}"
            logger.error(f"Request {request_id}: {error_msg}", exc_info=True)
            results.append({"attribute_name": item.attribute_name, "status": "error", "message": error_msg})

    if all_ok:
        return {"status": "success", "message": "All settings processed.", "details": results}
    else:
        return {"status": "partial_success", "message": "Some settings failed.", "details": results}

@router.get("/facts", response_model=List[ApiMemoryEntry])
async def get_user_facts_endpoint(x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    if not _ethos_core:
        logger.error("/v1/user/facts: EthosCore (via _ethos_core) not available.")
        raise HTTPException(status_code=503, detail="Eidos system (EthosCore) not ready.")

    raw_actual_user_id = x_user_id or "unknown_user" # Fallback to "unknown_user" if header is None

    # Normalize user_id
    actual_user_id = raw_actual_user_id.lower().strip().replace(" ", "_") if raw_actual_user_id else "unknown_user"
    if not actual_user_id: # Should not happen if raw_actual_user_id has a fallback, but as a safeguard
        actual_user_id = "unknown_user"    # Avoid processing for generic user IDs that don't typically store facts
    if actual_user_id in ["unknown_user", "api_guest_user", "default_user"]:
        logger.info(f"Request for user facts from a generic user context ('{actual_user_id}'). Returning empty list.")
        return []

    logger.info(f"API: Request for user facts for user_id (normalized): '{actual_user_id}' (Raw X-User-Id was: '{raw_actual_user_id}').")

    try:
        # Assuming get_all_user_facts returns a list of dicts or Pydantic models (GenericMemoryEntry)
        user_facts_raw: List[MemoryEntry] = await _ethos_core.get_all_user_facts(user_id=actual_user_id)


        validated_facts: List[ApiMemoryEntry] = []
        for fact_data_item in user_facts_raw:
            try:
                # If fact_data_item is already a dict, directly validate it with ApiMemoryEntry
                if isinstance(fact_data_item, dict):
                    validated_facts.append(ApiMemoryEntry(**fact_data_item))
                # If it's a Pydantic model (like GenericMemoryEntry), convert to dict then validate
                elif hasattr(fact_data_item, 'model_dump'): # Pydantic v2+
                    validated_facts.append(ApiMemoryEntry(**fact_data_item.model_dump()))
                elif hasattr(fact_data_item, 'dict'): # Pydantic v1
                    validated_facts.append(ApiMemoryEntry(**fact_data_item.dict()))
                else:
                    logger.warning(f"Skipping non-dict/non-Pydantic fact data for user '{actual_user_id}': {type(fact_data_item)}")
            except ValidationError as ve: # Catch Pydantic validation errors for individual items
                logger.error(f"Validation error for a user fact (user: {actual_user_id}): {ve.errors()}. Data: {fact_data_item}")
                # Optionally, decide if one invalid item should stop the whole request or just be skipped

        logger.info(f"Returning {len(validated_facts)} facts for user '{actual_user_id}'.")
        # jsonable_encoder might not be strictly necessary if validated_facts contains pure Pydantic models
        # and FastAPI handles their serialization correctly with response_model.
        # However, using it provides an explicit conversion step.
        return JSONResponse(content=jsonable_encoder(validated_facts))

    except HTTPException as http_exc: # Re-raise known HTTPExceptions
        raise http_exc
    except Exception as e:
        logger.error(f"API: Error fetching user facts for '{actual_user_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error fetching user facts.")
