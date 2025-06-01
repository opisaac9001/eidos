from typing import Dict, Any, Optional, List
import logging # Keep logging if used, though get_logger is preferred
from dataclasses import dataclass

from eidos_agent.core.config import Config
from eidos_agent.modules.ethos_core.core import EthosCore
from eidos_agent.modules.logos_core.handler import LogosCore
from eidos_agent.modules.pathos_interface import PathosInterface
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
                # conversation_history is already part of metadata_from_extraction
                # Ensure it's passed within request_metadata
                
                # The metadata_from_extraction already contains 'conversation_history'
                # from the extract_input_to_eidos_format function.
                # We just need to pass this directly.
                
                response_from_pathos = await self.pathos_interface.generate_response(
                    user_input=text_content,
                    image_data_b64=image_content_b64,
                    document_text=document_text,
                    request_metadata=metadata_from_extraction # This already contains conversation_history
                )

                logger.debug("<-- Exiting Pathos routing block.")
                return RoutingResult(
                    success=response_from_pathos.get('success', False),
                    content=response_from_pathos.get('content', '[No response content from Pathos]'),
                    metadata=response_from_pathos.get('metadata', {})
                )
            elif input_type in ['voice', 'sensor']:
                 logger.warning(f"Routing for input type '{input_type}' not fully implemented yet.")
                 return RoutingResult(success=False, content=f"Handling for input type '{input_type}' is not implemented.")
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