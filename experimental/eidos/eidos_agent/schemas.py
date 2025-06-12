"""
Central Pydantic models and schemas for Eidos agent API and data structures.

This module defines the data structures used for API request/response validation
and for internal data representation within the Eidos agent.
"""
from pydantic import BaseModel, Field, validator # Added validator
from typing import List, Optional, Dict, Any, Literal, Union
import uuid
import time
from datetime import datetime # Added datetime

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

# --- THIS IS THE IMPORTANT MODEL FOR THE /agent/learnings ENDPOINT ---
class MemoryEntry(BaseModel): # Ensure this is a Pydantic BaseModel
    id: str
    timestamp: str
    type: Literal[
        'interaction', 
        'context_summary', 
        'ambient_log', 
        'presence',
        'dream', 
        'reflection', 
        'feedback', 
        'system', 
        'task_outcome',
        'ha_interaction', 
        'info_query_time', 
        'info_query_math',
        'info_query_weather', 
        'info_query_wolfram_query', 
        'info_query_other',
        'task_failure', 
        'task_fallback_wa', 
        'document_chunk', 
        'vision_analysis',
        'sensor_reading', 
        'motion_event', 
        'daily_briefing',
        'pending_context_document',
        'user_fact', 
        'world_knowledge', 
        'learned_correction',       # This was present
        'proactive_action_record', 
        'queued_discussion_point',
        'learned_feedback_insight',   
        'suggestion_reflection'  
    ]
    content: str
    embedding: Optional[List[float]] = None 
    metadata: Dict[str, Any] = Field(default_factory=dict) 
    salience: Optional[float] = None
# --- END IMPORTANT MODEL ---

class DreamEntryResponse(BaseModel):
    id: str
    timestamp: str
    content: str
    dream_image_url: Optional[str] = None
    dream_seed_summary: Optional[str] = None

class ModelList(BaseModel):
    object: str = "list"
    data: List[ModelCard] = []

class ClearUserMemoryRequest(BaseModel):
    user_id: str

class FeedbackRequest(BaseModel):
    interaction_id: Optional[str] = None
    user_id: str
    last_user_input: str
    last_pathos_response: str
    feedback_type: Literal["positive", "negative", "correction", "suggestion", "other"]
    rating: Optional[int] = None
    feedback_text: Optional[str] = None
    suggested_response: Optional[str] = None

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


# --- ChatState Model (moved from models/chat_storage.py) ---
class ChatState(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for the chat")
    timestamp: datetime = Field(default_factory=datetime.now)
    systemPrompt: str = Field(default="You are a helpful assistant")
    conversation: List[ChatMessage] = Field(default_factory=list)
    selectedModel: str = Field(default="eidos-agent")
    title: Optional[str] = None
    userId: str = Field(..., description="User ID associated with this chat")
    isArchived: bool = False

    class Config:
        json_schema_extra = { # Kept for potential use, though Config is Pydantic v2 style
            "example": {
                "id": "chat_123",
                "timestamp": "2024-01-20T12:00:00Z",
                "systemPrompt": "You are a helpful assistant",
                "conversation": [
                    {"role": "user", "content": "Hello", "metadata": None},
                    {"role": "assistant", "content": "Hi there!", "metadata": None}
                ],
                "selectedModel": "eidos-agent",
                "title": "Sample Chat",
                "userId": "user123",
                "isArchived": False
            }
        }

    @validator('conversation', pre=True)
    @classmethod
    def ensure_conversation_list(cls, v):
        if v is None: return []
        return v

    @validator('systemPrompt', pre=True)
    @classmethod
    def ensure_system_prompt(cls, v):
        if not v: return "You are a helpful assistant"
        return v

    @validator('selectedModel', pre=True)
    @classmethod
    def ensure_model(cls, v):
        if not v: return "eidos-agent"
        return v

class ApiMemoryEntry(BaseModel):
    """A simplified memory entry model for API responses."""
    id: str
    timestamp: str
    type: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    salience: Optional[float] = None

