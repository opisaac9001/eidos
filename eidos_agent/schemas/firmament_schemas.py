from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class NPCProfile(BaseModel):
    """
    Represents the profile of a Non-Player Character (NPC) in the simulation.
    """
    npc_id: str = Field(..., description="Unique identifier for the NPC.")
    name: str = Field(..., description="Full name of the NPC.")

    appearance: Optional[str] = Field(default=None, description="Evocative physical description of the NPC.")
    role_in_scene: Optional[str] = Field(default=None, description="NPC's current role or reason for being in the scene.")
    personality_summary: Optional[str] = Field(default=None, description="Key personality traits or demeanor summary.")
    relationship_to_pathos: Optional[str] = Field(default="stranger", description="How the NPC knows or perceives Pathos (e.g., 'stranger', 'old friend', 'colleague').")
    current_disposition_towards_pathos: Optional[str] = Field(default="neutral", description="NPC's current attitude towards Pathos (e.g., friendly, wary, hostile).")

    # Internal state or more detailed attributes can be added as needed
    # current_mood_state: Optional[str] = None # NPC's own mood
    # known_facts: List[str] = Field(default_factory=list)
    # dialogue_style_hint: Optional[str] = None

class SimulationContext(BaseModel):
    """
    Describes Pathos's current situation within the Firmament simulation.
    """
    location_name: str = Field(..., description="The name of Pathos's current location.")
    location_description: Optional[str] = Field(default=None, description="A brief description of the current location.")
    time_of_day_in_simulation: Optional[str] = Field(default=None, description="Simulated time of day, e.g., 'morning', 'afternoon', 'evening', 'late night'.")
    current_event_or_activity: Optional[str] = Field(default=None, description="The ongoing event or Pathos's primary activity in the simulation, e.g., 'attending a lecture', 'working at a cafe'.")
    present_npcs: List[NPCProfile] = Field(default_factory=list, description="List of NPCs currently present and relevant in the scene with Pathos.")
    ambient_details: List[str] = Field(default_factory=list, description="Notable ambient details or environmental factors, e.g., 'rain is falling lightly', 'loud music playing'.")
    # Other contextual elements like current world events, interactive objects, etc.
    # world_event_flags: List[str] = Field(default_factory=list)

class NPCInteractionInput(BaseModel):
    """
    Data sent to FirmamentModule when Pathos speaks to an NPC.
    """
    pathos_utterance: str = Field(..., description="What Pathos said to the NPC.")
    npc_id: str = Field(..., description="The ID of the NPC Pathos is addressing.")
    # Optional: Pass additional context if Firmament needs it beyond its internal state
    # For example, Pathos's current mood might influence NPC's perception.
    # pathos_mood_snapshot: Optional[Dict[str, Any]] = None

class NPCInteractionOutput(BaseModel):
    """
    Data returned from FirmamentModule after an NPC interaction, containing the NPC's response.
    This was previously named FirmamentNPCResponse.
    """
    npc_id: str = Field(..., description="The ID of the NPC who responded.")
    npc_response_utterance: str = Field(..., description="The NPC's dialogue response.")
    # Optionally, Firmament can indicate if the broader simulation context changed due to the interaction.
    # This could be a full SimulationContext object or just a summary string.
    updated_simulation_context_summary: Optional[str] = Field(default=None, description="Brief summary of any significant changes to the simulation context as a result of the interaction.")
    # For more detailed changes:
    # new_simulation_context_state: Optional[SimulationContext] = None
