import httpx
import io
import json
from typing import Optional, Dict, Any

from eidos_agent.core.config import Config, EidosTTSConfig, VALID_PITCH_SPEED_VALUES, VALID_GENDER_VALUES # Import constants
from eidos_agent.utils.logger import get_logger

logger = get_logger(__name__)

# This mapping is crucial. It should map the string values Eidos uses
# (and are defined in VALID_PITCH_SPEED_VALUES in config.py)
# to the integers 1-5 that the SparkTTS API server's /tts/create endpoint expects.
# This is the reverse of what SparkTTS's internal LEVELS_MAP_UI might be doing.
# We need to define this based on how SparkTTS's API server maps its integer inputs.
# Assuming a direct mapping for now:
# "very_low": 1, "low": 2, "moderate": 3, "high": 4, "very_high": 5
# Let's get this from the SparkTTS API server's `LEVELS_MAP_UI` if possible,
# or define it based on its expected behavior.
# The SparkTTS API server code shows:
# pitch: int = Form(...),  # 1-5
# pitch_val = LEVELS_MAP_UI[pitch]
# This means the API endpoint *receives* an int (1-5) and then *maps it* to a string for the SparkTTS library.
# So, Eidos should send an INT.

# Let's assume Eidos config will store strings, and we map them to ints here.
# OR, Eidos config stores ints, and we just pass them.
# The current EidosTTSConfig stores strings: default_pitch_str, default_speed_str.

# Mapping from string config values to integer API values for SparkTTS
TTS_PARAM_STRING_TO_INT_MAP = {
    "very_low": 1,
    "low": 2,
    "moderate": 3,
    "high": 4,
    "very_high": 5
}


class ExternalTTSService:
    def __init__(self, config: Config):
        self.eidos_tts_config: Optional[EidosTTSConfig] = config.EIDOS_TTS
        self.http_client: Optional[httpx.AsyncClient] = None

        if self.eidos_tts_config and self.eidos_tts_config.get('api_url'):
            self.http_client = httpx.AsyncClient(timeout=90.0)
            logger.info(f"ExternalTTSService initialized to use API at: {self.eidos_tts_config['api_url']}")
        else:
            logger.warning("ExternalTTSService: api_url not configured. TTS will not function.")

    def is_available(self) -> bool:
        return self.http_client is not None

    async def synthesize(
        self,
        text: str,
        gender_override: Optional[str] = None,
        pitch_override: Optional[str] = None, # Eidos GUI/API might send string
        speed_override: Optional[str] = None, # Eidos GUI/API might send string
    ) -> Optional[bytes]:
        if not self.is_available() or not self.eidos_tts_config or not self.http_client:
            logger.error("ExternalTTSService.synthesize called but service/config/client not available.")
            return None
        if not text or not text.strip():
            logger.warning("TTS synthesis requested for empty text.")
            return None

        api_url = self.eidos_tts_config['api_url']
        tts_create_endpoint = f"{api_url.rstrip('/')}/tts/create"

        # Get string values from overrides or Eidos config defaults
        gender_str = gender_override if gender_override else self.eidos_tts_config.get('default_gender', 'female')
        pitch_str = pitch_override if pitch_override else self.eidos_tts_config.get('default_pitch_str', 'moderate')
        speed_str = speed_override if speed_override else self.eidos_tts_config.get('default_speed_str', 'moderate')

        # Validate string values
        if gender_str not in VALID_GENDER_VALUES:
            logger.warning(f"Invalid gender string '{gender_str}', using default.")
            gender_str = self.eidos_tts_config.get('default_gender', 'female')
        if pitch_str not in VALID_PITCH_SPEED_VALUES:
            logger.warning(f"Invalid pitch string '{pitch_str}', using default.")
            pitch_str = self.eidos_tts_config.get('default_pitch_str', 'moderate')
        if speed_str not in VALID_PITCH_SPEED_VALUES:
            logger.warning(f"Invalid speed string '{speed_str}', using default.")
            speed_str = self.eidos_tts_config.get('default_speed_str', 'moderate')

        # Convert validated strings to integers for the SparkTTS API
        pitch_int = TTS_PARAM_STRING_TO_INT_MAP.get(pitch_str, 3) # Default to 3 (moderate) if somehow not found
        speed_int = TTS_PARAM_STRING_TO_INT_MAP.get(speed_str, 3) # Default to 3 (moderate)

        form_data = {
            'text': text,
            'gender': gender_str, # Gender is already a string 'female' or 'male'
            'pitch': str(pitch_int), # SparkTTS API expects integer for pitch, sent as string in form
            'speed': str(speed_int)  # SparkTTS API expects integer for speed, sent as string in form
        }

        try:
            logger.info(f"ExternalTTSService: Sending POST request to {tts_create_endpoint} with form data: {form_data}")
            response = await self.http_client.post(tts_create_endpoint, data=form_data)
            logger.debug(f"ExternalTTSService: SparkTTS API response status: {response.status_code}")

            if response.status_code == 200:
                audio_bytes = await response.aread()
                logger.info(f"ExternalTTSService: Synthesis successful. Received {len(audio_bytes)} audio bytes.")
                return audio_bytes
            else:
                error_content_bytes = await response.aread()
                error_content_str = error_content_bytes.decode('utf-8', errors='replace')
                logger.error(f"Error from SparkTTS API ({response.status_code}). Response content: {error_content_str}")
                try:
                    error_detail_json = json.loads(error_content_str)
                    error_message = error_detail_json.get('detail', str(error_detail_json))
                    if isinstance(error_message, list) and error_message:
                        error_message = "; ".join([f"{e.get('loc', ['unknown_field'])[-1]}: {e.get('msg')}" for e in error_message])
                except json.JSONDecodeError:
                    error_message = error_content_str if error_content_str else f"HTTP Error {response.status_code}"
                logger.error(f"Formatted error message from SparkTTS API: {error_message}")
                return None
        except httpx.ConnectError as e:
            logger.error(f"ExternalTTSService: ConnectionError when calling SparkTTS API at {tts_create_endpoint}: {e}", exc_info=True)
            return None
        except httpx.TimeoutException as e:
            logger.error(f"ExternalTTSService: Timeout when calling SparkTTS API at {tts_create_endpoint}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"ExternalTTSService: Unexpected error during TTS synthesis request: {e}", exc_info=True)
            return None

    async def close(self):
        if self.http_client:
            await self.http_client.aclose()
            logger.info("ExternalTTSService HTTP client closed.")