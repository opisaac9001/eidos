from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid

class NPCProfile(BaseModel):
    npc_id: str = Field(default_factory=lambda: f"npc_{uuid.uuid4().hex}")
    name: str
    role_description: Optional[str] = None # e.g., "Barista at The Daily Grind", "Lead Developer at Client AlphaTech"

    # For NPC LLM: concise summary of personality, speaking style, key knowledge.
    # Example: "You are John, a friendly but busy barista. You are always polite and efficient. You sometimes make small talk about the weather or local events."
    persona_summary_prompt: Optional[str] = None

    relationship_strength: float = Field(default=0.0) # e.g., -1.0 (hostile) to 1.0 (very friendly), 0.0 is neutral

    # Facts Pathos has learned or inferred about this NPC
    known_facts_by_pathos: List[str] = Field(default_factory=list)

    # Pathos's private notes or reflections about this NPC (not shared with NPC LLM directly)
    pathos_notes_on_npc: Optional[str] = None

    # Optional: An LLM-generated summary of interaction history. Could be updated periodically.
    interaction_history_summary: Optional[str] = None

    last_interaction_ts: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        # For Pydantic v1, use this for default values on update, etc.
        # For Pydantic v2, behavior is more straightforward with default_factory.
        # validate_assignment = True # Might be useful if fields are updated directly
        pass

# Example Usage (not part of the file, just for illustration):
# npc_data = {
#     "name": "Bob The Barista",
#     "role_description": "Morning barista at The Daily Grind",
#     "persona_summary_prompt": "You are Bob, a cheerful but slightly sarcastic barista. You know regular customers by name. You often recommend the daily special."
# }
# new_npc = NPCProfile(**npc_data)
# print(new_npc.model_dump_json(indent=2)) # Use .model_dump_json() in Pydantic v2, .json() in v1
