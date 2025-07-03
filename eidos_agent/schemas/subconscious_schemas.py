from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime

class SubconsciousThought(BaseModel):
    """
    Represents a thought retrieved from the Subconscious Node.
    """
    # SubconsciousNode might generate its own IDs, or Eidos client can assign them upon receipt.
    # For now, assume it's assigned by the client or is part of the raw data from the node.
    thought_id: str = Field(..., description="Unique identifier for the subconscious thought.")
    timestamp_recorded: datetime = Field(..., description="Timestamp when the thought was recorded by the Subconscious Node (UTC).")
    content: str = Field(..., description="The textual content of the thought.")

    # Optional metadata that might come from or be inferred about the thought:
    salience_score: Optional[float] = Field(default=None, description="Estimated salience or intensity of the thought (if scored by Subconscious Node or later processing).")
    mood_at_thought: Optional[Dict[str, Any]] = Field(default=None, description="A snapshot of the Subconscious Node's internal mood when this thought occurred.")
    keywords: List[str] = Field(default_factory=list, description="Keywords extracted from the thought content.")
    emotional_tags: List[str] = Field(default_factory=list, description="Emotional tags associated with the thought (e.g., 'anxiety', 'curiosity', 'fleeting_joy').")
    source_trigger: Optional[str] = Field(default=None, description="What might have triggered this thought (if known by Subconscious Node, e.g., 'recent_conversation_snippet', 'ambient_stimulus').")

class SubconsciousInjectType(BaseModel):
    """
    Schema for injecting context into the Subconscious Node.
    Matches the expected payload for endpoints like /inject/conversation, /inject/action, /inject/dream_fragment.
    """
    content: str = Field(..., description="The textual content to be injected as context.")

class SubconsciousControlState(BaseModel):
    """
    Schema for controlling the operational state of the Subconscious Node.
    Matches the expected payload for the /control/state endpoint.
    """
    node_state: str = Field(..., description="The desired operational state (e.g., 'AWAKE_THINKING', 'SLEEPING_DREAMING', 'IDLE').")
    # Used when transitioning to SLEEPING_DREAMING to provide a summary for dream generation.
    daily_summary: Optional[str] = Field(default=None, description="A summary of Pathos's recent experiences to seed dream generation.")

# Optional: Schema for mood synchronization if Eidos pushes mood to Subconscious Node
# class SubconsciousMoodSyncPayload(BaseModel):
#     """
#     Schema for syncing Pathos's main mood state to the Subconscious Node.
#     Matches the expected payload for the /control/mood endpoint.
#     """
#     mood_aspects: Dict[str, float] = Field(..., description="Key-value pairs of mood dimensions and their scores.")
#     timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of when this mood state was generated in Eidos.")
