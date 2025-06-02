from datetime import datetime
from typing import List, Dict, Any, Optional, Union # Added Union
from pydantic import BaseModel, Field, validator  # Use validator for Pydantic v1
import uuid

class ChatMessage(BaseModel):
    role: str
    content: Optional[Union[str, List[Dict[str, Any]]]] = None # Allow content to be string or list for multimodal
    metadata: Optional[Dict[str, Any]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None # Added for tool call history
    tool_call_id: Optional[str] = None # Added for tool result history
    
    @validator('role')
    @classmethod
    def validate_role(cls, v):
        allowed_roles = {'user', 'assistant', 'system', 'tool'} # Added 'tool'
        if v not in allowed_roles:
            raise ValueError(f'Role must be one of {allowed_roles}')
        return v

class ChatState(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for the chat")
    timestamp: datetime = Field(default_factory=datetime.now)
    systemPrompt: str = Field(default="You are a helpful assistant")
    conversation: List[ChatMessage] = Field(default_factory=list) # Changed from 'messages' to 'conversation'
    selectedModel: str = Field(default="eidos-agent")
    title: Optional[str] = None
    userId: str = Field(..., description="User ID associated with this chat")
    isArchived: bool = False

    class Config:
        json_schema_extra = {
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

    @validator('conversation', pre=True)  # Changed from 'messages'
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