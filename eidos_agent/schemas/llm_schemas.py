from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal # Added Literal

# Adopt the more detailed ToolCall/FunctionCall from existing schemas for OpenAI compatibility
class FunctionCall(BaseModel):
    name: str
    arguments: str # Arguments are often a JSON string

class ToolCall(BaseModel):
    id: str # Tool call ID, to be used in ToolResponseMessage
    type: Literal["function"] = "function"
    function: FunctionCall

class LLMOutput(BaseModel):
    """
    Represents the structured output parsed from the Main Pathos LLM's response.
    It distinguishes different types of actions Pathos might take.
    """
    raw_text: str # The complete raw text response from the LLM
    dialogue_to_user: Optional[str] = None
    dialogue_to_npc: Optional[str] = None
    target_npc_id: Optional[str] = None # Must be present if dialogue_to_npc is set
    tool_calls: Optional[List[ToolCall]] = None # Updated to use the more detailed ToolCall
    # Could add fields for internal monologue, emotional expression hints, etc.
    # E.g., internal_thought: Optional[str] = None

class LLMResponsePayload(BaseModel):
    """
    A standardized wrapper for the raw response received from any LLM API call.
    Used by the LLMClient.
    """
    content: Optional[str] = None # The textual content from the LLM
    error_message: Optional[str] = None # If an error occurred during the call
    status_code: Optional[int] = None # HTTP status code of the LLM API response
    # Optional: usage_statistics: Optional[Dict[str, int]] = None # e.g., prompt_tokens, completion_tokens
    # Optional: raw_response_data: Optional[Dict[str, Any]] = None # For debugging or advanced use cases

    def success(self) -> bool:
        return self.content is not None and self.error_message is None and \
               (self.status_code is None or 200 <= self.status_code < 300)

# Note: The ChatMessage model, which might include ToolCall, will be in oai_schemas.py
# from .oai_schemas import ChatMessage
