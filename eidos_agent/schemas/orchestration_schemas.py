from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# These would be imported from their respective schema files once those are created
# For now, using Dict[str, Any] as placeholders.
# from .ethos_schemas import MoodState, Memory, PersonaProfile
# from .chronos_schemas import Activity
# from .firmament_schemas import SimulationContext
# from .subconscious_schemas import SubconsciousThought

class MainLLMPromptContext(BaseModel):
    """
    Comprehensive context provided to the Main Pathos LLM for generating a response or action.
    """
    user_input: str
    conversation_history: List[Dict[str, str]] = Field(default_factory=list) # e.g., [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

    # Context from EthosCore
    current_mood: Optional[Dict[str, Any]] # Placeholder for MoodState model
    recent_memories: Optional[List[Dict[str, Any]]] = Field(default_factory=list) # Placeholder for List[Memory]
    persona_profile: Optional[Dict[str, Any]] # Placeholder for PersonaProfile model

    # Context from ChronosEngine
    current_activity: Optional[Dict[str, Any]] # Placeholder for Activity model

    # Context from FirmamentModule
    simulation_context: Optional[Dict[str, Any]] # Placeholder for SimulationContext model

    # Context from SubconsciousNode
    significant_subconscious_thoughts: Optional[List[Dict[str, Any]]] = Field(default_factory=list) # Placeholder for List[SubconsciousThought]

    # Optional: System alerts or notifications Pathos should be aware of
    # system_alerts: Optional[List[str]] = Field(default_factory=list)

    # Optional: Explicit goals or tasks Pathos is currently working on
    # current_goals: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
