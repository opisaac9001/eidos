from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal, Union 
import uuid
import time

class FunctionCall(BaseModel):
    name: str
    arguments: str

class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: FunctionCall

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[Union[str, List[Dict[str, Any]]]] = None 

    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class UserSettingItem(BaseModel):
    attribute_name: str
    attribute_value: Any 
    user_statement_context: Optional[str] = "User updated setting via GUI."

class UserSettingsRequest(BaseModel):
    user_id: str 
    settings: List[UserSettingItem]    

class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False
    user: Optional[str] = None

class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: Optional[Literal["stop", "length", "tool_calls", "content_filter", "null"]] = "stop"

class ChatCompletionUsage(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4()}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[ChatCompletionUsage] = None

class ModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "eidos-project"

class DreamEntryResponse(BaseModel):
    id: str
    timestamp: str
    content: str
    dream_image_url: Optional[str] = None # This will be the web-accessible URL
    # Add any other metadata you want to expose, e.g., seed memory summary
    dream_seed_summary: Optional[str] = None

class ModelList(BaseModel):
    object: str = "list"
    data: List[ModelCard] = []

class ClearUserMemoryRequest(BaseModel):
    user_id: str

# --- Ensure FeedbackRequest is defined ---
class FeedbackRequest(BaseModel):
    interaction_id: Optional[str] = None
    user_id: str
    last_user_input: str
    last_pathos_response: str
    feedback_type: Literal["positive", "negative", "correction", "suggestion", "other"]
    rating: Optional[int] = None
    feedback_text: Optional[str] = None
    suggested_response: Optional[str] = None
# --- END FeedbackRequest Definition ---

# --- Streaming Response Models (Placeholders) ---
class DeltaMessage(BaseModel):
    role: Optional[Literal["system", "user", "assistant", "tool"]] = None
    content: Optional[str] = None

class ChatCompletionChunkChoice(BaseModel):
    index: int = 0
    delta: DeltaMessage
    finish_reason: Optional[Literal["stop", "length", "tool_calls", "content_filter", "null"]] = None

class ChatCompletionChunk(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4()}")
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChunkChoice]

class KnowledgeVerificationLogEntry(BaseModel):
    fact_id: Optional[str] = None
    original_statement_snippet: str
    verification_timestamp: str
    verification_status: str 
    new_statement: Optional[str] = None
    superseded_by_fact_id: Optional[str] = None
    verification_details: Optional[str] = None    