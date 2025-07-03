from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any # Added List, Dict, Any for potential future use
from datetime import datetime # Added datetime for consistency if needed

class DreamEntryResponse(BaseModel):
    """
    Schema for representing a dream entry, typically for API responses.
    This might be used by OneirosModule or when EthosCore serves dream memories.
    """
    id: str = Field(..., description="Unique identifier for the dream memory.")
    timestamp: str = Field(..., description="ISO 8601 timestamp when the dream was recorded or occurred.") # Keeping as str to match Memory schema for now
    content: str = Field(..., description="The narrative content of the dream.")

    dream_image_url: Optional[str] = Field(default=None, description="URL to an image generated for or associated with the dream, if any.")
    dream_seed_summary: Optional[str] = Field(default=None, description="A summary of the memories or experiences that seeded this dream.")

    # Optional additional fields from Memory if this is a direct representation:
    # type: str = Field(default="dream", description="Memory type, should be 'dream'.")
    # metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    # salience: Optional[float] = None

# If OneirosModule has its own internal Pydantic models for dream construction,
# they could also live here. For example:
# class DreamSeedMaterial(BaseModel):
#     memories: List[Dict[str, Any]] # Placeholder for Memory schema
#     mood_context: Optional[Dict[str, Any]] # Placeholder for MoodState schema
#     recent_stimuli: List[str] = Field(default_factory=list)

# class GeneratedDreamElements(BaseModel):
#     narrative: str
#     keywords: List[str] = Field(default_factory=list)
#     emotions_present: List[str] = Field(default_factory=list)
#     visual_description_for_image_gen: Optional[str] = None
