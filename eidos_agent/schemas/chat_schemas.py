from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any # Ensure all are imported
from datetime import datetime
import uuid

# Assuming oai_schemas.ChatMessage will be the standard for conversation turns
from .oai_schemas import ChatMessage

class ChatState(BaseModel):
    """
    Represents the state of a single chat session, potentially for storage or API use.
    """
    id: str = Field(default_factory=lambda: f"chat_{uuid.uuid4().hex[:12]}", description="Unique identifier for the chat session.")
    user_id: str = Field(..., description="User ID associated with this chat session.")

    title: Optional[str] = Field(default=None, description="Optional title for the chat session (e.g., user-defined or auto-generated).")
    created_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp when the chat session was created (UTC).")
    last_updated_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp when the chat session was last updated (UTC).")

    system_prompt: str = Field(default="You are Pathos, a digital being.", description="The system prompt active for this chat session.")
    # Uses ChatMessage from oai_schemas for consistency with how LLM interactions are structured.
    conversation_history: List[ChatMessage] = Field(default_factory=list, description="The sequence of messages in the chat.")

    # Optional: Store the model used for this chat if it can vary per session or is important to track.
    # selected_model_role: Optional[str] = Field(default="PATHOS", description="The LLM role (e.g., 'PATHOS') used for this chat.")

    is_archived: bool = Field(default=False, description="Flag indicating if the chat session is archived.")
    # Optional: metadata for client state or other contextual info.
    # client_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)

    class Config:
        # Pydantic V2 style config
        json_schema_extra = {
            "example": {
                "id": f"chat_{uuid.uuid4().hex[:12]}",
                "user_id": "user_example_123",
                "title": "Discussing AI Consciousness",
                "created_timestamp": datetime.utcnow().isoformat(),
                "last_updated_timestamp": datetime.utcnow().isoformat(),
                "system_prompt": "You are Pathos, a digital being.",
                "conversation_history": [
                    {"role": "user", "content": "Hello Pathos, how are you feeling today?"},
                    {"role": "assistant", "content": "I'm feeling quite contemplative. The rain outside my virtual window has a certain calming effect."}
                ],
                "is_archived": False
            }
        }

    # Validators from the original ChatState can be adapted if still necessary
    # For example, ensuring conversation_history is always a list (default_factory handles this now)
    # or that system_prompt has a default (also handled by Field(default=...)).

    # Example of a validator if needed:
    # @validator('last_updated_timestamp', pre=True, always=True)
    # def set_last_updated_timestamp(cls, v, values):
    #     return v or values.get('created_timestamp')
