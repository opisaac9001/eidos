from typing import Dict, Any, Optional, List
import logging # Keep logging if used, though get_logger is preferred
from dataclasses import dataclass

from eidos_agent.core.config import Config
from eidos_agent.persona_logic.ethos_core.core import EthosCore # Already updated
from eidos_agent.persona_logic.logos_core.handler import LogosCore # Already updated
from eidos_agent.llm_integrations.pathos_interface import PathosInterface # Updated import
from eidos_agent.utils.logger import get_logger

logger = get_logger(__name__)

@dataclass
class RoutingResult:
    success: bool
    content: str
    metadata: Optional[Dict[str, Any]] = None

class InputRouter:
    def __init__(
        self,
        config: Config,
        ethos_core: EthosCore,
        logos_core: LogosCore,
        pathos_interface: PathosInterface
    ):
        self.config = config
        self.ethos_core = ethos_core
        self.logos_core = logos_core
        self.pathos_interface = pathos_interface
        logger.info("InputRouter initialized (Direct Vision Processing Strategy with User ID passthrough).")

    async def route_input(self, input_data: Dict[str, Any]) -> RoutingResult:
        input_type = input_data.get('type', 'text')
        text_content = input_data.get('text_content', "")
        image_content_b64 = input_data.get('image_content_b64')
        document_text = input_data.get('document_text')
        metadata_from_extraction = input_data.get('metadata', {})

        log_content_snippet = str(text_content)[:50] if text_content else "[No text content]"
        if image_content_b64:
            log_content_snippet += f" | Image data length: {len(image_content_b64)}"
        if document_text: # Log document presence
            log_content_snippet += f" | Document text length: {len(document_text)}"

        # Log max_tokens_override if present in the incoming metadata
        max_tokens_override_log = metadata_from_extraction.get('max_tokens_override')
        if max_tokens_override_log is not None:
            log_content_snippet += f" | MaxTokensOverride: {max_tokens_override_log}"

        logger.debug(f"Routing input type: {input_type}, content preview: {log_content_snippet}..., User ID from metadata: {metadata_from_extraction.get('user_id')}")

        try:
            if input_type == 'text' or input_type == 'multimodal_input':
                logger.debug(f"--> Routing '{input_type}' input to PathosInterface.")
                
                # Extract user_id from input_data metadata
                user_id_for_pathos = input_data.get('metadata', {}).get('user_id', 'unknown_router_user') # Add a fallback

                response_from_pathos = await self.pathos_interface.generate_response(
                    user_id=user_id_for_pathos, # <<< ADD THIS ARGUMENT
                    user_input=text_content,
                    image_data_b64=image_content_b64,
                    document_text=document_text,
                    request_metadata=metadata_from_extraction
                )

                logger.debug("<-- Exiting Pathos routing block.")
                return RoutingResult(
                    success=response_from_pathos.get('success', False),
                    content=response_from_pathos.get('content', '[No response content from Pathos]'),
                    metadata=response_from_pathos.get('metadata', {})
                )
            elif input_type == 'voice':
                    # CONCEPTUAL DESIGN FOR VOICE INPUT:
                    # 1. Expected input_data fields:
                    #    - type: "voice"
                    #    - audio_content_b64: str (Base64 encoded audio)
                    #    - audio_format: str (e.g., "wav", "mp3")
                    #    - user_id: str (from metadata)
                    #    - timestamp: str (ISO 8601)
                    #    - Optional: language_hint: str
                    #
                    # 2. Processing Flow:
                    #    - InputRouter receives 'voice' type.
                    #    - Delegate to a new 'VoiceProcessingService' (or LogosCore if STT is a tool).
                    #    - VoiceProcessingService.transcribe(audio_data, format, hint) calls STT engine.
                    #    - STT returns transcribed_text.
                    #    - InputRouter then re-routes this transcribed_text as a 'text' input:
                    #      await self.pathos_interface.generate_response(
                    #          user_id=input_data.metadata.user_id,
                    #          user_input=transcribed_text,
                    #          request_metadata=input_data.metadata
                    #      )
                    #
                    # 3. Output: The RoutingResult from pathos_interface.
                    # 4. Error Handling: STT failures logged; specific error message returned.
                    logger.warning(f"Routing for input type 'voice' not functionally implemented yet. See conceptual design in comments.")
                    return RoutingResult(success=False, content="Voice input handling is not yet implemented.")

            elif input_type == 'sensor':
                    # CONCEPTUAL DESIGN FOR SENSOR INPUT:
                    # 1. Expected input_data fields:
                    #    - type: "sensor"
                    #    - sensor_id: str
                    #    - sensor_type: str (e.g., "temperature", "motion", "gps_location")
                    #    - value: Any (sensor reading)
                    #    - unit: Optional[str]
                    #    - user_id: Optional[str] (or system ID)
                    #    - timestamp: str (ISO 8601)
                    #    - location_hint: Optional[str]
                    #
                    # 2. Processing Flow:
                    #    - InputRouter receives 'sensor' type.
                    #    - Option A: Publish to a system-wide event bus (if exists).
                    #    - Option B: Direct delegation:
                    #        - To Firmament (e.g., an EnvironmentState manager or event handler):
                    #            - firmament.process_sensor_data(input_data)
                    #            - Firmament updates its internal state, may trigger other events (e.g., WORLD_EVENT).
                    #        - To EthosCore:
                    #            - ethos_core.add_memory_entry(type="sensor_reading", content=json.dumps(input_data), metadata=...)
                    #    - (Aisthesis module might be involved in receiving sensor data from external sources before it hits InputRouter).
                    #
                    # 3. Output: Likely an acknowledgment (e.g., {"status": "sensor_data_processed"}) or None,
                    #    as direct user response is not typical for sensor readings. Internal effects are key.
                    # 4. Error Handling: Log malformed data or processing failures.
                    logger.warning(f"Routing for input type 'sensor' not functionally implemented yet. See conceptual design in comments.")
                    return RoutingResult(success=False, content="Sensor input handling is not yet implemented.")
            else:
                logger.warning(f"Unsupported input type received: {input_type}")
                return RoutingResult(success=False, content=f"Unsupported input type: {input_type}")

        except Exception as e:
            logger.error(f"Routing error for input: {log_content_snippet}...", exc_info=True)
            error_meta = {'original_input_type': input_type, 'original_content_snippet': log_content_snippet}
            return RoutingResult(
                success=False,
                content=f"System error during routing: {str(e)}",
                metadata=error_meta
            )