from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime

class HexusScore(BaseModel):
    """Represents a single dimension of Pathos's Hexus (emotional/state) scores."""
    name: str = Field(..., description="Name of the Hexus dimension (e.g., 'joy', 'stress', 'curiosity').")
    value: float = Field(..., description="Current score of the Hexus dimension (typically 0.0 to 1.0).")

class MoodState(BaseModel):
    """Describes Pathos's overall mood, derived from Hexus scores."""
    valence: float = Field(..., description="Overall emotional valence (-1.0 negative to 1.0 positive).")
    arousal: float = Field(..., description="Overall physiological arousal (-1.0 calm to 1.0 excited).")
    name: str = Field(..., description="Categorical name of the mood (e.g., 'happy', 'curious', 'anxious', 'neutral').")
    detailed_hexus_scores: List[HexusScore] = Field(default_factory=list, description="Snapshot of all current Hexus scores contributing to this mood.")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp when this mood state was generated.")

# Incorporating the rich Literal types from the existing MemoryEntry
# and keeping timestamp as string for now, assuming it's stored as ISO string.
# Conversion to datetime can happen at load time in EthosCore/MemoryStorage.
class Memory(BaseModel):
    """
    Represents a single memory entry in Pathos's mind.
    """
    id: str = Field(..., description="Unique identifier for the memory.")
    timestamp: str = Field(..., description="ISO 8601 timestamp when the event occurred or memory was recorded (UTC).")
    type: Literal[
        'interaction',
        'chat_interaction', # Explicitly add if used distinctly from 'interaction'
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
        'pending_context_document', # Should this type persist or be transient?
        'user_fact',
        'world_knowledge',
        'learned_correction',
        'proactive_action_record',
        'queued_discussion_point',
        'learned_feedback_insight',
        'suggestion_reflection',
        # Adding types from our new design, if not covered
        'observation', # General observation by Pathos
        'npc_dialogue', # Specific log of NPC dialogue turn
        'firmament_activity_log', # Log of Pathos's activity in Firmament
        'reflection_insight', # Output of a reflection cycle (distinct from 'reflection' type if 'reflection' is process log)
        'aspiration' # Pathos's goals
    ] = Field(..., description="Categorical type of the memory.")
    content: str = Field(..., description="The textual content or description of the memory.")
    embedding: Optional[List[float]] = Field(default=None, description="Vector embedding of the memory content.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional structured data about the memory (e.g., user_id, involved_entities, location, mood_at_time).")
    salience: Optional[float] = Field(default=0.5, description="Importance or vividness of the memory (0.0 to 1.0+).")
    is_archived: bool = Field(default=False, description="Whether the memory has been archived (soft delete).")
    last_accessed_timestamp: Optional[str] = Field(default=None, description="ISO 8601 timestamp of when the memory was last accessed.")


class PersonaDirective(BaseModel):
    """A core belief, principle, or operational guideline for Pathos."""
    directive_id: str = Field(..., description="Unique identifier for the directive.")
    text: str = Field(..., description="The content of the directive.")
    source: str = Field(default="core", description="Origin of the directive (e.g., 'core', 'learned_reflection', 'user_defined').")
    is_active: bool = Field(default=True)

class Trait(BaseModel):
    """A personality trait of Pathos."""
    name: str = Field(..., description="Name of the trait (e.g., 'extraversion', 'curiosity', 'openness').")
    value: Any = Field(..., description="Value of the trait (can be float, string, bool depending on the trait's nature).")
    description: Optional[str] = Field(default=None, description="Brief description of what this trait represents.")

class PersonaProfile(BaseModel):
    """A snapshot of Pathos's overall personality configuration."""
    core_directives: List[PersonaDirective] = Field(default_factory=list)
    learned_directives: List[PersonaDirective] = Field(default_factory=list)
    traits: List[Trait] = Field(default_factory=list)
    self_description_summary: Optional[str] = Field(default=None, description="A brief self-description Pathos might generate.")

class InteractionLog(BaseModel):
    """
    Structured log of a complete interaction sequence, used for creating memories.
    """
    interaction_id: str = Field(..., description="Unique ID for this interaction log.")
    timestamp: datetime = Field(..., description="Start time of the interaction (timezone-aware UTC).")
    user_id: Optional[str] = Field(default=None)
    pathos_mood_at_start: MoodState
    conversation_turns: List[Dict[str, str]] = Field(default_factory=list) # e.g., [{"role": "user", "content": "..."}]
    # Optional:
    # triggered_tool_calls: Optional[List[LLMToolCall]] # from llm_schemas
    # resulting_hexus_changes: Optional[List[HexusScore]]
    summary_of_outcome: Optional[str] = None
    involved_npc_ids: List[str] = Field(default_factory=list)


# Schemas from the old file that relate to Ethos/Memory API
class ApiMemoryEntry(BaseModel):
    """A simplified memory entry model for API responses, typically for listings."""
    id: str
    timestamp: str
    type: str # Keep as string for API, no need for Literal if it's just for display
    content: str
    metadata: Optional[Dict[str, Any]] = None
    salience: Optional[float] = None

class ClearUserMemoryRequest(BaseModel):
    user_id: str

class KnowledgeVerificationLogEntry(BaseModel): # Related to world_knowledge
    fact_id: Optional[str] = None
    original_statement_snippet: str
    verification_timestamp: str # ISO Format
    verification_status: str # e.g., "verified_unchanged", "verified_updated", "refuted", "needs_further_review"
    new_statement: Optional[str] = None # If the fact was updated
    superseded_by_fact_id: Optional[str] = None # If this fact is now replaced by another
    verification_details: Optional[str] = None # LLM reasoning or source of verification
    verified_by: Optional[str] = Field(default="system_knowledge_upkeep")
