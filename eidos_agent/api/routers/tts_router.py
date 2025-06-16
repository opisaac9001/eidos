"""
API Router for Text-to-Speech (TTS) services for the Eidos Agent.
"""
import logging
import io
from typing import Optional, Any, Dict
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Assuming ExternalTTSService is in this location
from eidos_agent.services.external_tts_service import ExternalTTSService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/tts",
    tags=["TTS"]
)

# Module-level variable for dependency injection
_eidos_tts_service: Optional[ExternalTTSService] = None
_temp_audio_cache: Optional[Dict[str, bytes]] = None # Added for get_tts_audio_chunk

def init_tts_router(tts_service: ExternalTTSService, temp_audio_cache: Dict[str, bytes]): # Added temp_audio_cache
    """
    Initializes the TTS router with an instance of the ExternalTTSService
    and the temporary audio cache.
    This function is called during application startup to inject dependencies.
    """
    global _eidos_tts_service, _temp_audio_cache
    _eidos_tts_service = tts_service
    _temp_audio_cache = temp_audio_cache
    logger.info("TTS Router initialized with ExternalTTSService instance and audio cache.")

# --- Pydantic Model for TTS Request ---
class TTSRequestAPI(BaseModel):
    text: str
    gender: Optional[str] = None
    pitch: Optional[str] = None
    speed: Optional[str] = None

# --- TTS Endpoints ---
@router.post("/synthesize")
async def synthesize_speech_api(request_data: TTSRequestAPI):
    """
    Synthesizes speech from text using the configured external TTS service.
    """
    if not _eidos_tts_service or not _eidos_tts_service.is_available():
        raise HTTPException(status_code=503, detail="TTS service is not available or not configured.")

    logger.info(f"TTS Router: Synthesis request for text: '{request_data.text[:50]}...' G:{request_data.gender} P:{request_data.pitch} S:{request_data.speed}")
    try:
        speed_val = None
        if request_data.speed:
            try: speed_val = float(request_data.speed)
            except ValueError: raise HTTPException(status_code=422, detail="Invalid speed value, must be a number.")

        audio_bytes = await _eidos_tts_service.synthesize(
            text=request_data.text,
            speed_override=speed_val
            # gender_override and pitch_override would be passed if _eidos_tts_service supports them
        )
        if audio_bytes:
            return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/wav") # Assuming WAV for now
        else:
            logger.error("TTS synthesis failed to produce audio (external service returned None or empty).")
            raise HTTPException(status_code=500, detail="TTS synthesis failed to produce audio (external service).")
    except Exception as e:
        logger.error(f"Error during TTS synthesis API call: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS synthesis error: {str(e)}")

@router.get("/audio_chunk/{chunk_id}")
async def get_tts_audio_chunk(chunk_id: str):
    """
    Retrieves a previously cached TTS audio chunk by its ID.
    Chunks are typically removed from cache after being served once.
    """
    if _temp_audio_cache is None:
        logger.error("TTS audio cache not initialized in TTS Router.")
        raise HTTPException(status_code=503, detail="TTS audio cache not available.")

    logger.debug(f"TTS Router: Request for audio chunk ID: {chunk_id}. Cache size: {len(_temp_audio_cache)}")
    audio_bytes = _temp_audio_cache.pop(chunk_id, None) # Use pop to remove after retrieval

    if audio_bytes:
        logger.info(f"TTS Router: Serving audio chunk ID: {chunk_id}, Length: {len(audio_bytes)} bytes.")
        return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/wav")
    else:
        logger.warning(f"TTS Router: Audio chunk ID: {chunk_id} not found in cache or already served.")
        raise HTTPException(status_code=404, detail="Audio chunk not found or already served.")
