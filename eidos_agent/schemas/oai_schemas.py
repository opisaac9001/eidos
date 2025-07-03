"""
Pydantic models for ensuring OpenAI API compatibility for certain Eidos endpoints.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal, Union
import uuid
import time

# Imported from llm_schemas.py as it's the new standard internal representation
# If oai_schemas needs a distinct version, it can be redefined here,
# but ideally, they align if LLMOutput.tool_calls uses this structure.
from .llm_schemas import ToolCall, FunctionCall # FunctionCall is part of ToolCall here

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[Union[str, List[Dict[str, Any]]]] = None # Content can be list for vision models
    tool_calls: Optional[List[ToolCall]] = None # Standardized ToolCall
    tool_call_id: Optional[str] = None # For tool responses
    name: Optional[str] = None # For function/tool name if role is 'tool'
    metadata: Optional[Dict[str, Any]] = None # Eidos-specific metadata, not part of OAI spec

class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None # Let provider use default if None
    stream: Optional[bool] = False
    user: Optional[str] = None # OAI spec: A unique identifier representing your end-user
    # OAI tool parameters
    tools: Optional[List[Dict[str, Any]]] = None # e.g., [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]
    tool_choice: Optional[Union[str, Dict[str, Any]]] = None # e.g., "none", "auto", {"type": "function", "function": {"name": "my_function"}}

class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: Optional[Literal["stop", "length", "tool_calls", "content_filter", "null"]] = "stop"

class ChatCompletionUsage(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:16]}") # Shortened ID
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str # Model name that generated the response
    choices: List[ChatCompletionChoice]
    usage: Optional[ChatCompletionUsage] = None
    # system_fingerprint: Optional[str] = None # Present in OAI responses

class ModelCard(BaseModel):
    id: str # The model identifier, e.g., "eidos-main-llm", "gpt-4"
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "eidos-project"
    # Eidos specific extensions:
    description: Optional[str] = None
    capabilities: Optional[List[str]] = None # e.g., ["chat", "tools", "vision"]

class ModelList(BaseModel):
    object: str = "list"
    data: List[ModelCard] = []

# Streaming related models
class DeltaMessage(BaseModel):
    role: Optional[Literal["system", "user", "assistant", "tool"]] = None
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None # For streaming tool calls

class ChatCompletionChunkChoice(BaseModel):
    index: int = 0
    delta: DeltaMessage
    finish_reason: Optional[Literal["stop", "length", "tool_calls", "content_filter", "null"]] = None
    # logprobs: Optional[Any] = None # Not yet supported here

class ChatCompletionChunk(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:16]}") # Shortened ID
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str # Model name
    choices: List[ChatCompletionChunkChoice]
    # system_fingerprint: Optional[str] = None # Present in OAI responses
    # usage: Optional[ChatCompletionUsage] = None # Usage is typically not in chunks, but in the final non-streaming response
