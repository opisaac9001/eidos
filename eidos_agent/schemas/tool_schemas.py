from pydantic import BaseModel, Field
from typing import Any, Optional, Dict, List # Ensure List and Dict are imported if used by Any

class ToolResult(BaseModel):
    """
    Represents the outcome of a tool execution by LogosCore.
    This structure is returned to PathosInterface to be fed back to the Main Pathos LLM.
    """
    tool_name: str = Field(..., description="The name of the tool that was executed.")
    # Corresponds to LLMToolCall.call_id if the LLM provided one, for matching requests to results.
    call_id: Optional[str] = Field(default=None, description="Optional unique ID of the tool call this result corresponds to.")

    status: str = Field(..., description="Outcome status of the tool execution (e.g., 'success', 'error', 'pending_further_action', 'user_input_required').")

    # The actual result payload. Can be a simple string, a structured dict, or even a list.
    # For example, a web search tool might return a list of search snippets.
    # A calendar tool might return a confirmation message or details of a created event.
    result_payload: Any = Field(..., description="The data returned by the tool. Its structure depends on the tool.")

    error_details: Optional[str] = Field(default=None, description="Details if the tool execution resulted in an error.")

    # Optional: A human-readable summary of the result, suitable for direct inclusion in an LLM prompt.
    # If not provided, PathosInterface/PromptBuilder will need to format result_payload appropriately.
    result_summary_for_llm: Optional[str] = Field(default=None, description="A pre-formatted string summary of the result, ready for LLM consumption.")

# Note: The LLMToolCall schema (which LogosCore would receive from PathosInterface)
# is defined in llm_schemas.py as it's part of the LLM's output structure.
# from .llm_schemas import LLMToolCall # Example of how it might be referenced.
