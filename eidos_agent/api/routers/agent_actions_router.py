import logging
import uuid # For request_id in receive_feedback
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Request, File, UploadFile, Header # Request might not be needed if not used
from fastapi.responses import JSONResponse

# Pydantic models from eidos_agent.schemas
from eidos_agent.schemas import FeedbackRequest

# Core Eidos components (to be injected)
from eidos_agent.modules.pathos_interface import PathosInterface
from eidos_agent.modules.ethos_core.core import EthosCore
from eidos_agent.modules.logos_core.handler import LogosCore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["Agent Actions"])

# Module-level globals for dependencies
_pathos_interface: Optional[PathosInterface] = None
_ethos_core: Optional[EthosCore] = None
_logos_core: Optional[LogosCore] = None

def init_agent_actions_router(
    pathos: PathosInterface,
    ethos: EthosCore,
    logos: LogosCore
):
    """Initializes the Agent Actions router with necessary Eidos core components."""
    global _pathos_interface, _ethos_core, _logos_core

    _pathos_interface = pathos
    _ethos_core = ethos
    _logos_core = logos

    logger.info("Agent Actions Router initialized with Eidos core components.")

@router.post("/feedback", status_code=202)
async def receive_feedback(feedback_data: FeedbackRequest, x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    request_id = str(uuid.uuid4())
    logger.info(f"Request {request_id}: /v1/feedback. User from header: '{x_user_id}'")

    if not _pathos_interface or not _ethos_core:
        logger.error("Agent Actions Router: PathosInterface or EthosCore not initialized.")
        raise HTTPException(status_code=503, detail="Eidos system not ready for feedback.")

    feedback_dict = feedback_data.model_dump(exclude_unset=True)

    # Standardize user_id: payload > header > fallback
    if 'user_id' not in feedback_dict or not feedback_dict['user_id']: # if user_id not in payload or empty
        if x_user_id: # use header if available
            feedback_dict['user_id'] = x_user_id
        else: # fallback
            feedback_dict['user_id'] = 'api_guest_user'

    logger.info(f"Request {request_id}: Feedback for user '{feedback_dict.get('user_id')}': {str(feedback_dict)[:500]}...")

    try:
        await _pathos_interface.process_feedback(feedback_dict)
        logger.info(f"Request {request_id}: Feedback for '{feedback_dict.get('user_id')}' passed to PathosInterface.")
        return {"message": "Feedback received and queued.", "feedback_log_id": request_id}
    except Exception as e: # pragma: no cover
        logger.error(f"Request {request_id}: Error processing feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error processing feedback: {str(e)}")

@router.post("/documents/upload", status_code=200)
async def upload_document(file: UploadFile = File(..., description="Document (PDF, DOCX, TXT)"), x_user_id: Optional[str] = Header(None, alias="X-User-Id")): # pragma: no cover
    if not _logos_core:
        logger.error("Agent Actions Router: LogosCore not initialized for document upload.")
        raise HTTPException(status_code=503, detail="Eidos system (LogosCore) not ready.")

    logger.info(f"Doc upload: '{file.filename}' ({file.content_type}, {getattr(file, 'size', 'unknown')} bytes) for user '{x_user_id or 'unknown_user'}'.")

    try:
        file_content = await file.read()
    except Exception as e:
        logger.error(f"Error reading uploaded file '{file.filename}': {e}", exc_info=True)
        raise HTTPException(status_code=422, detail=f"Error reading file: {e}")
    finally:
        if hasattr(file, 'file') and hasattr(file.file, 'close') and callable(file.file.close):
            file.file.close() # Ensure the file is closed

    if not file_content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = await _logos_core.process_uploaded_document(file_content, file.filename, user_id=x_user_id)
        if result.get("success"):
            return JSONResponse(content={"success": True, "message": "Document processed.", "extracted_text": result.get("extracted_text")})
        # If not success, raise HTTPException with details from result
        error_message = result.get("message", "Document processing failed without specific error.")
        logger.warning(f"Document upload for '{file.filename}' failed: {error_message}")
        raise HTTPException(status_code=500, detail=error_message)
    except HTTPException as http_exc:
        raise http_exc # Re-raise if it's already an HTTPException
    except Exception as e:
        logger.error(f"Unexpected error processing doc '{file.filename}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error during document processing.")

@router.get("/briefing", status_code=200)
async def get_daily_briefing_endpoint(x_user_id: Optional[str] = Header(None, alias="X-User-Id")): # pragma: no cover
    if not _ethos_core or not _logos_core:
        logger.error("Agent Actions Router: EthosCore or LogosCore not initialized for briefing.")
        raise HTTPException(status_code=503, detail="Eidos system (core briefing components) not ready.")

    user_id = x_user_id or "unknown_user" # Fallback if header is None
    logger.info(f"Request for /v1/briefing for user '{user_id}'.")

    try:
        briefing_result = await _logos_core.get_or_generate_daily_briefing(user_id_context=user_id)
        if briefing_result.get("success"):
            return JSONResponse(content=briefing_result)
        else:
            # Log warning but still return the (potentially partial) result as per original logic
            logger.warning(f"Briefing for '{user_id}' not fully successful: {briefing_result.get('message')}")
            return JSONResponse(content=briefing_result)
    except HTTPException as http_exc:
        raise http_exc # Re-raise known HTTPExceptions
    except Exception as e:
        logger.error(f"Unexpected error in /v1/briefing for '{user_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error processing briefing.")
