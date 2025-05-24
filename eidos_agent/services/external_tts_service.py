# In eidos_agent/services/external_tts_service.py

import httpx
import json
from typing import Optional, Dict, Any, Literal # Added Literal

from eidos_agent.core.config import Config, EidosTTSConfig # Ensure EidosTTSConfig is updated if new env vars are added
from eidos_agent.utils.logger import get_logger

logger = get_logger(__name__)

class ExternalTTSService:
    def __init__(self, config: Config):
        self.tts_config: Optional[EidosTTSConfig] = config.EIDOS_TTS
        self.http_client: Optional[httpx.AsyncClient] = None

        if self.tts_config and self.tts_config.get('api_url'):
            client_timeout = float(self.tts_config.get('timeout', 60.0))
            self.http_client = httpx.AsyncClient(timeout=client_timeout)
            logger.info(f"ExternalTTSService (Kokoro Adapter) initialized to use API at: {self.tts_config['api_url']}")
            if not self.tts_config.get('voice_id'): # KOKORO_TTS_VOICE_ID
                logger.warning("ExternalTTSService: 'voice_id' for Kokoro TTS is not configured. TTS might fail or use a server default.")
            if not self.tts_config.get('model_id'): # KOKORO_TTS_MODEL_ID (expected to be "kokoro" or similar)
                logger.warning("ExternalTTSService: 'model_id' for Kokoro TTS is not configured. Ensure it's set (e.g., to 'kokoro').")
        else:
            logger.warning("ExternalTTSService: api_url not configured for TTS. Service will not function.")

    def is_available(self) -> bool:
        return self.http_client is not None and self.tts_config is not None

    async def synthesize(self, text: str, *, speed_override: float | None = None): # speed_override is float
        if not self.is_available():
            logger.error("ExternalTTSService.synthesize called but service is not available.")
            return None
        
        assert self.tts_config is not None
        assert self.http_client is not None

        tts_endpoint = self.tts_config['api_url'] 

        headers = {"Content-Type": "application/json", "accept": "application/json"} # Added "accept" header
        
        kokoro_model_id = self.tts_config.get('model_id', 'kokoro') # Default to "kokoro" if KOKORO_TTS_MODEL_ID not set
        kokoro_voice_id = self.tts_config.get('voice_id') # This MUST be a valid voice from Kokoro (e.g., "af_heart")
        
        # Get response_format from config, default to "mp3" as per Kokoro example
        kokoro_response_format = self.tts_config.get('response_format', 'mp3')

        current_speed_float = speed_override if speed_override is not None else self.tts_config.get('speed', 1.0)

        kokoro_speed = current_speed_float # Or int(current_speed_float) if strictly integer

        kokoro_lang_code = self.tts_config.get('lang_code', 'en-US') # Add KOKORO_TTS_LANG_CODE to .env, default to en-US

        default_normalization_opts = {
            "normalize": True,
            "unit_normalization": False,
            "url_normalization": True,
            "email_normalization": True,
            "optional_pluralization_normalization": True,
            "phone_normalization": True
        }
        # Get from config; if it's None or not a dict, use defaults.
        # If it is a dict, merge with defaults to ensure all keys are present if Kokoro needs them.
        configured_norm_opts = self.tts_config.get('normalization_options')
        if isinstance(configured_norm_opts, dict):
            final_normalization_opts = {**default_normalization_opts, **configured_norm_opts}
        else:
            final_normalization_opts = default_normalization_opts
            if configured_norm_opts is not None: # Log if it was set but not a dict
                 logger.warning(f"Configured 'normalization_options' is not a dictionary, using defaults. Value was: {configured_norm_opts}")


        payload_for_kokoro: Dict[str, Any] = {
            "model": kokoro_model_id,
            "input": text,
            "voice": kokoro_voice_id,
            "response_format": kokoro_response_format,
            "download_format": kokoro_response_format,
            "speed": kokoro_speed,
            "stream": False,
            "return_download_link": False,
            "lang_code": kokoro_lang_code,
            "normalization_options": final_normalization_opts # <<< USE THE FINAL OBJECT
        }

        if not kokoro_voice_id:
            logger.error("KOKORO_TTS_VOICE_ID is not set. Cannot make TTS request.")
            return None # Critical field

        request_timeout = float(self.tts_config.get('timeout', 60.0))

        try:
            logger.info(f"ExternalTTSService (Kokoro): Sending POST to {tts_endpoint}. Payload: {json.dumps(payload_for_kokoro)}")
            response = await self.http_client.post(
                tts_endpoint,
                headers=headers,
                json=payload_for_kokoro,
                timeout=request_timeout
            )
            logger.debug(f"ExternalTTSService (Kokoro): TTS API response status: {response.status_code}")

            if response.status_code == 200:
                # Kokoro might return JSON with a base64 audio string OR direct audio bytes.
                # The example curl implies it might expect `accept: application/json` and then parse JSON.
                # However, if `return_download_link` is false and `stream` is false, it might send direct audio.
                # Let's try to get raw bytes first, as that's what OpenAI TTS does.
                content_type = response.headers.get("content-type", "").lower()
                logger.info(f"ExternalTTSService (Kokoro): Synthesis successful. Content-Type: {content_type}")

                audio_bytes = await response.aread()
                if not audio_bytes:
                    logger.warning(f"Kokoro TTS API returned 200 OK but with an empty response body for text: '{text[:50]}...'")
                    return None
                
                # If Kokoro sends JSON with base64 audio (less likely for direct audio/speech endpoint but possible)
                # if 'application/json' in content_type:
                #     try:
                #         json_response = json.loads(audio_bytes.decode())
                #         if 'audio_content_base64' in json_response: # Hypothetical key
                #             audio_bytes = base64.b64decode(json_response['audio_content_base64'])
                #         else:
                #             logger.warning("Kokoro TTS returned JSON but no known audio field.")
                #             return None
                #     except Exception as e:
                #         logger.error(f"Failed to parse JSON audio response from Kokoro: {e}")
                #         return None

                # Assuming direct audio bytes for now, like OpenAI
                if kokoro_response_format == "wav" and (not audio_bytes.startswith(b'RIFF')):
                    logger.warning(f"Expected WAV format but received data doesn't start with RIFF header. Bytes: {audio_bytes[:20]}")
                
                return audio_bytes
            
            else: 
                # Log the full error response from Kokoro for 400 errors
                error_content_str = ""
                try:
                    error_content_bytes = await response.aread()
                    error_content_str = error_content_bytes.decode('utf-8', errors='replace')
                    logger.error(f"Error from Kokoro TTS API ({response.status_code}). Full Response: {error_content_str}")
                    # Try to parse JSON detail if present
                    error_detail_json = json.loads(error_content_str)
                    error_message_detail = error_detail_json.get('detail') # Kokoro example shows "detail"
                    if isinstance(error_message_detail, list) and error_message_detail: # FastAPI validation errors
                        error_message = f"Kokoro TTS Validation Error: {error_message_detail[0].get('msg')} for field {error_message_detail[0].get('loc')}"
                    elif isinstance(error_message_detail, str):
                        error_message = f"Kokoro TTS API Error: {error_message_detail}"
                    else:
                        error_message = f"Kokoro TTS API Error ({response.status_code}): {error_content_str[:200]}"
                except json.JSONDecodeError:
                    error_message = f"Kokoro TTS API Error ({response.status_code}), non-JSON response: {error_content_str[:200]}"
                except Exception as e_parse:
                    error_message = f"Kokoro TTS API Error ({response.status_code}), error parsing response: {str(e_parse)}"

                logger.error(f"Formatted error message from Kokoro TTS API: {error_message}")
                return None

        # ... (rest of exception handling: Timeout, ConnectError, etc. as before) ...
        except httpx.TimeoutException as e:
            logger.error(f"ExternalTTSService (Kokoro): Timeout when calling TTS API at {tts_endpoint}: {e}", exc_info=True)
            return None
        except httpx.ConnectError as e:
            logger.error(f"ExternalTTSService (Kokoro): ConnectionError when calling TTS API at {tts_endpoint}: {e}", exc_info=True)
            return None
        except httpx.RequestError as e:
            logger.error(f"ExternalTTSService (Kokoro): RequestError with TTS API at {tts_endpoint}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"ExternalTTSService (Kokoro): Unexpected error during TTS synthesis request: {e}", exc_info=True)
            return None

    async def close(self):
        if self.http_client:
            await self.http_client.aclose()
            logger.info("ExternalTTSService HTTP client closed.")