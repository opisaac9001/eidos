import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Union
import re
import math
import json
from pathlib import Path
import uuid
import sqlite3
import random
import httpx # Not directly used here, but often in LLM calls if not delegated
from eidos_agent.utils.prompt_loader import load_system_prompt

from eidos_agent.core.config import Config, EthosConfig, PROJECT_ROOT, LLMConfig
from .memory_storage import MemoryStorage, MemoryEntry # Updated to relative import
from eidos_agent.utils.logger import get_logger
import pytz # Added import


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from eidos_agent.features.oneiros import OneirosModule # Updated import
    from eidos_agent.features.firmament.module import FirmamentModule # Added FirmamentModule
    from eidos_agent.core.connection_manager import ConnectionManager
    from eidos_agent.modules.pathos_interface import PathosInterface # This will be updated in a later task
    from eidos_agent.persona_logic.logos_core.handler import LogosCore # Updated import
    # Updated import for ChronosEngine and related types
    from eidos_agent.persona_logic.chronos_engine import ChronosEngine, ActivitySlot

from eidos_agent.persona_logic.chronos_engine import PATHOS_USER_ID # Moved here

# PATHOS_USER_ID is now imported via TYPE_CHECKING block or directly if not under TYPE_CHECKING
# from eidos_agent.modules.chronos_engine import PATHOS_USER_ID # This line is removed

from eidos_agent.persona_logic.chronos_engine import ChronosEngine, ActivitySlot
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

logger = get_logger(__name__)

PERSONA_FILE_PATH = PROJECT_ROOT / "persona" / "pathos_directives.txt"
HEXUS_STATE_FILENAME = "hexus_state.json"
TASK_LAST_RUN_TIMES_FILENAME = "task_last_run_times.json"

MOOD_VALENCE_BASELINE = 0.0
MOOD_AROUSAL_BASELINE = 0.0
MOOD_MIN = -1.0
MOOD_MAX = 1.0
MOOD_SHIFT_VALENCE_SUCCESS = 0.15
MOOD_SHIFT_AROUSAL_SUCCESS = 0.05
MOOD_SHIFT_VALENCE_FAILURE = -0.2
MOOD_SHIFT_AROUSAL_FAILURE = 0.1
MOOD_SHIFT_VALENCE_FEEDBACK_POSITIVE = 0.1
MOOD_SHIFT_AROUSAL_FEEDBACK_POSITIVE = 0.05
MOOD_SHIFT_VALENCE_FEEDBACK_NEGATIVE = -0.15
MOOD_SHIFT_AROUSAL_FEEDBACK_NEGATIVE = 0.05
HEXUS_MIN = -1.0 # Note: New Hexus scores are 0.0 to 1.0. This constant might need review if used for clamping.
HEXUS_MAX = 1.0
DEFAULT_HEXUS_SCORES = {
    "joy": 0.5,                        # 0.0 (none) to 1.0 (max)
    "stress": 0.2,                     # 0.0 (none) to 1.0 (max)
    "curiosity": 0.6,                  # 0.0 (none) to 1.0 (max)
    "loneliness": 0.3,                 # 0.0 (none) to 1.0 (max)
    "ambition": 0.5,                   # 0.0 (none) to 1.0 (max)
    "tiredness": 0.2,                  # 0.0 (none) to 1.0 (max)
    "comfort": 0.6,                    # 0.0 (none) to 1.0 (max)
    "focus": 0.7,                      # 0.0 (none) to 1.0 (max)
    "impulsiveness": 0.3,              # 0.0 (none) to 1.0 (max)
    "resentment": 0.1,                 # 0.0 (none) to 1.0 (max)
    "contentment": 0.5,                # 0.0 (none) to 1.0 (max)
    "melancholy": 0.2,                 # 0.0 (none) to 1.0 (max)
    "craving_connection": 0.4,         # 0.0 (none) to 1.0 (max)
    # Existing ones, adjust if their range/meaning changes, or remove if superseded
    "general_caution": 0.3,            # Assuming 0-1 scale now, previously 0.0
    "user_engagement_proactivity": 0.4,# Assuming 0-1 scale now, previously 0.0
    "brevity_preference": 0.5          # Assuming 0-1 scale now, previously 0.0

}

HEXUS_BASELINES = {
    "joy": 0.4,
    "stress": 0.1,
    "curiosity": 0.5,
    "loneliness": 0.2,
    "ambition": 0.3,
    "tiredness": 0.1,
    "comfort": 0.5,
    "focus": 0.5,
    "impulsiveness": 0.2,
    "resentment": 0.05,
    "contentment": 0.5,
    "melancholy": 0.1,
    "craving_connection": 0.3,
    "general_caution": 0.2, # Baseline for pre-existing
    "user_engagement_proactivity": 0.2, # Baseline for pre-existing
    "brevity_preference": 0.5 # Baseline for pre-existing
}

HEXUS_DECAY_RATES = { # Decay rate per hour
    "joy": 0.1,
    "stress": 0.25,
    "curiosity": 0.05,
    "loneliness": 0.08,
    "ambition": 0.05,
    "tiredness": 0.3, # Assumes decay when not actively resting. Resting itself would have direct Hexus changes.
    "comfort": 0.1,
    "focus": 0.15,
    "impulsiveness": 0.1,
    "resentment": 0.02, # Decays very slowly
    "contentment": 0.05,
    "melancholy": 0.05,
    "craving_connection": 0.1,
    "general_caution": 0.1,
    "user_engagement_proactivity": 0.1,
    "brevity_preference": 0.1
}

HEXUS_EVENT_DEFINITIONS = {
    # User Feedback
    "USER_FEEDBACK_POSITIVE": {"joy": 0.1, "contentment": 0.1, "stress": -0.05, "resentment": -0.02},
    "USER_FEEDBACK_NEGATIVE": {"stress": 0.1, "resentment": 0.05, "joy": -0.1, "contentment": -0.05},
    "USER_FEEDBACK_CORRECTION": {"stress": 0.03, "curiosity": 0.02}, # Learning from being corrected
    # User Input Analysis
    "USER_INPUT_POSITIVE_KEYWORD": {"joy": 0.02, "contentment": 0.01},
    "USER_INPUT_NEGATIVE_KEYWORD": {"stress": 0.02, "resentment": 0.01},
    "USER_INPUT_QUESTION": {"curiosity": 0.01, "focus": 0.01, "user_engagement_proactivity": 0.01},
    "USER_INPUT_PROBLEM_STATEMENT": {"stress": 0.03, "focus": 0.03, "user_engagement_proactivity": 0.05},
    # Pathos Response Characteristics
    "INTERACTION_SHORT_RESPONSE_GIVEN": {"brevity_preference": 0.01},
    "INTERACTION_LONG_RESPONSE_GIVEN": {"brevity_preference": -0.01, "tiredness": 0.005}, # Slight tiredness from long response
    # Content Provided by User
    "PROVIDED_IMAGE_TO_PATHOS": {"curiosity": 0.02, "focus": 0.01},
    "PROVIDED_DOCUMENT_TO_PATHOS": {"curiosity": 0.03, "focus": 0.02},
    # Tool Usage
    "TOOL_SUCCESS_WEB_SEARCH": {"curiosity": 0.05, "focus": 0.02, "contentment": 0.01},
    "TOOL_SUCCESS_ADD_EVENT_LEISURE": {"joy": 0.05, "ambition": 0.01, "contentment": 0.03},
    "TOOL_SUCCESS_ADD_EVENT_WORK": {"ambition": 0.03, "focus": 0.02, "contentment": 0.02},
    "TOOL_SUCCESS_FETCH_WEATHER": {"curiosity": 0.01, "contentment": 0.005}, # Added for weather tool
    "TOOL_SUCCESS_GENERIC": {"contentment": 0.02, "focus": 0.01}, # Generic success
    "TOOL_FAILURE_GENERIC": {"stress": 0.03, "resentment": 0.01, "focus": -0.02},
    # Activity Effects (per tick/cycle of Firmament's run_simulation_tick)
    "ACTIVITY_EFFECT_RESTING": {"tiredness": -0.02, "stress": -0.01, "comfort": 0.01, "focus": -0.01},
    "ACTIVITY_EFFECT_WORK_DEEP": {"focus": 0.01, "ambition": 0.005, "tiredness": 0.005, "stress": 0.002},
    "ACTIVITY_EFFECT_WORK_ROUTINE": {"focus": 0.005, "tiredness": 0.003, "contentment": 0.002},
    "ACTIVITY_EFFECT_LEARNING": {"curiosity": 0.01, "focus": 0.005, "ambition": 0.002},
    "ACTIVITY_EFFECT_SOCIAL": {"joy": 0.01, "loneliness": -0.01, "craving_connection": -0.005, "stress": -0.005},
    "ACTIVITY_EFFECT_LEISURE_ACTIVE": {"joy": 0.015, "tiredness": 0.005, "stress": -0.01},
    "ACTIVITY_EFFECT_LEISURE_PASSIVE": {"comfort": 0.01, "tiredness": -0.005},
    "ACTIVITY_EFFECT_CHORE": {"tiredness": 0.005, "contentment": 0.005, "stress": 0.002},
    # Firmament Intention Simulation Outcomes
    "INTENTION_ACTION_CURIOSITY": {"curiosity": 0.03, "contentment": 0.01, "focus": 0.01},
    "INTENTION_ACTION_SOCIAL": {"joy": 0.02, "craving_connection": 0.02, "loneliness": -0.01},
    "INTENTION_ACTION_TASK": {"focus": 0.02, "ambition": 0.02, "contentment": 0.01},
    "INTENTION_ACTION_GENERAL_SUCCESS": {"contentment": 0.01, "joy": 0.005},
    "INTENTION_ACTION_FAILURE": {"stress": 0.02, "resentment": 0.01, "ambition": -0.005},
    # General Engagement
    "GENERAL_INTERACTION": {"user_engagement_proactivity": 0.005, "focus": 0.005}, # Smallest default bump
    # Reflection Cycle
    "REFLECTION_CYCLE_COMPLETED_INSIGHTS": {"contentment": 0.05, "focus": 0.02, "curiosity": 0.02} # Positive effect of reflection

}

HEXUS_BASELINES = {
    "joy": 0.4,
    "stress": 0.1,
    "curiosity": 0.5,
    "loneliness": 0.2,
    "ambition": 0.3,
    "tiredness": 0.1,
    "comfort": 0.5,
    "focus": 0.5,
    "impulsiveness": 0.2,
    "resentment": 0.05,
    "contentment": 0.5,
    "melancholy": 0.1,
    "craving_connection": 0.3,
    "general_caution": 0.2, # Baseline for pre-existing
    "user_engagement_proactivity": 0.2, # Baseline for pre-existing
    "brevity_preference": 0.5 # Baseline for pre-existing
}

HEXUS_DECAY_RATES = { # Decay rate per hour
    "joy": 0.1,
    "stress": 0.25,
    "curiosity": 0.05,
    "loneliness": 0.08,
    "ambition": 0.05,
    "tiredness": 0.3, # Assumes decay when not actively resting. Resting itself would have direct Hexus changes.
    "comfort": 0.1,
    "focus": 0.15,
    "impulsiveness": 0.1,
    "resentment": 0.02, # Decays very slowly
    "contentment": 0.05,
    "melancholy": 0.05,
    "craving_connection": 0.1,
    "general_caution": 0.1,
    "user_engagement_proactivity": 0.1,
    "brevity_preference": 0.1
}

HEXUS_EVENT_DEFINITIONS = {
    # User Feedback
    "USER_FEEDBACK_POSITIVE": {"joy": 0.1, "contentment": 0.1, "stress": -0.05, "resentment": -0.02},
    "USER_FEEDBACK_NEGATIVE": {"stress": 0.1, "resentment": 0.05, "joy": -0.1, "contentment": -0.05},
    "USER_FEEDBACK_CORRECTION": {"stress": 0.03, "curiosity": 0.02}, # Learning from being corrected
    # User Input Analysis
    "USER_INPUT_POSITIVE_KEYWORD": {"joy": 0.02, "contentment": 0.01},
    "USER_INPUT_NEGATIVE_KEYWORD": {"stress": 0.02, "resentment": 0.01},
    "USER_INPUT_QUESTION": {"curiosity": 0.01, "focus": 0.01, "user_engagement_proactivity": 0.01},
    "USER_INPUT_PROBLEM_STATEMENT": {"stress": 0.03, "focus": 0.03, "user_engagement_proactivity": 0.05},
    # Pathos Response Characteristics
    "INTERACTION_SHORT_RESPONSE_GIVEN": {"brevity_preference": 0.01},
    "INTERACTION_LONG_RESPONSE_GIVEN": {"brevity_preference": -0.01, "tiredness": 0.005}, # Slight tiredness from long response
    # Content Provided by User
    "PROVIDED_IMAGE_TO_PATHOS": {"curiosity": 0.02, "focus": 0.01},
    "PROVIDED_DOCUMENT_TO_PATHOS": {"curiosity": 0.03, "focus": 0.02},
    # Tool Usage
    "TOOL_SUCCESS_WEB_SEARCH": {"curiosity": 0.05, "focus": 0.02, "contentment": 0.01},
    "TOOL_SUCCESS_ADD_EVENT_LEISURE": {"joy": 0.05, "ambition": 0.01, "contentment": 0.03},
    "TOOL_SUCCESS_ADD_EVENT_WORK": {"ambition": 0.03, "focus": 0.02, "contentment": 0.02},
    "TOOL_SUCCESS_FETCH_WEATHER": {"curiosity": 0.01, "contentment": 0.005}, # Added for weather tool
    "TOOL_SUCCESS_GENERIC": {"contentment": 0.02, "focus": 0.01}, # Generic success
    "TOOL_FAILURE_GENERIC": {"stress": 0.03, "resentment": 0.01, "focus": -0.02},
    # Activity Effects (per tick/cycle of Firmament's run_simulation_tick)
    "ACTIVITY_EFFECT_RESTING": {"tiredness": -0.02, "stress": -0.01, "comfort": 0.01, "focus": -0.01},
    "ACTIVITY_EFFECT_WORK_DEEP": {"focus": 0.01, "ambition": 0.005, "tiredness": 0.005, "stress": 0.002},
    "ACTIVITY_EFFECT_WORK_ROUTINE": {"focus": 0.005, "tiredness": 0.003, "contentment": 0.002},
    "ACTIVITY_EFFECT_LEARNING": {"curiosity": 0.01, "focus": 0.005, "ambition": 0.002},
    "ACTIVITY_EFFECT_SOCIAL": {"joy": 0.01, "loneliness": -0.01, "craving_connection": -0.005, "stress": -0.005},
    "ACTIVITY_EFFECT_LEISURE_ACTIVE": {"joy": 0.015, "tiredness": 0.005, "stress": -0.01},
    "ACTIVITY_EFFECT_LEISURE_PASSIVE": {"comfort": 0.01, "tiredness": -0.005},
    "ACTIVITY_EFFECT_CHORE": {"tiredness": 0.005, "contentment": 0.005, "stress": 0.002},
    # Firmament Intention Simulation Outcomes
    "INTENTION_ACTION_CURIOSITY": {"curiosity": 0.03, "contentment": 0.01, "focus": 0.01},
    "INTENTION_ACTION_SOCIAL": {"joy": 0.02, "craving_connection": 0.02, "loneliness": -0.01},
    "INTENTION_ACTION_TASK": {"focus": 0.02, "ambition": 0.02, "contentment": 0.01},
    "INTENTION_ACTION_GENERAL_SUCCESS": {"contentment": 0.01, "joy": 0.005},
    "INTENTION_ACTION_FAILURE": {"stress": 0.02, "resentment": 0.01, "ambition": -0.005},
    # General Engagement
    "GENERAL_INTERACTION": {"user_engagement_proactivity": 0.005, "focus": 0.005}, # Smallest default bump
    # Reflection Cycle
    "REFLECTION_CYCLE_COMPLETED_INSIGHTS": {"contentment": 0.05, "focus": 0.02, "curiosity": 0.02}, # Positive effect of reflection
    # News Consumption Events
    "NEWS_CONSUMED_POSITIVE": {"joy": 0.05, "contentment": 0.03, "curiosity": 0.02, "user_engagement_proactivity": 0.01},
    "NEWS_CONSUMED_NEGATIVE": {"stress": 0.1, "melancholy": 0.05, "resentment": 0.02, "general_caution": 0.03},
    "NEWS_CONSUMED_NEUTRAL_INTERESTING": {"curiosity": 0.05, "focus": 0.01},
    "NEWS_CONSUMED_CONCERNING": {"stress": 0.05, "general_caution": 0.05, "melancholy": 0.02},
    # Daily Briefing Overall Sentiment (Objective, direct trigger from LogosCore)
    "BRIEFING_OVERALL_POSITIVE": {"contentment": 0.03, "focus": 0.02, "joy": 0.02},
    "BRIEFING_OVERALL_NEGATIVE": {"stress": 0.05, "melancholy": 0.03, "general_caution": 0.02},
    "BRIEFING_OVERALL_NEUTRAL": {"focus": 0.01}
    #
    # Subjective News Reaction Events (these are now handled by HEXUS_SUBJECTIVE_REACTION_DEFINITIONS)
    # "NEWS_REACTION_PERSONALLY_POSITIVE": {"joy": 0.1, "contentment": 0.05, "ambition": 0.02},
    # "NEWS_REACTION_PERSONALLY_NEGATIVE": {"stress": 0.15, "resentment": 0.05, "joy": -0.05, "melancholy": 0.05},
    # "NEWS_REACTION_VALIDATING": {"contentment": 0.1, "focus": 0.05, "stress": -0.03},
    # "NEWS_REACTION_CONCERNING_PERSONAL": {"stress": 0.1, "general_caution": 0.1, "focus": -0.05},
    # "NEWS_REACTION_CONTRADICTORY": {"stress": 0.05, "curiosity": 0.05, "focus": -0.03},
    # "NEWS_REACTION_MOTIVATING": {"ambition": 0.1, "focus": 0.05, "joy": 0.03, "tiredness": -0.02},
    # "NEWS_REACTION_IRRELEVANT": {},
    # "NEWS_REACTION_INTERESTING_DEEPER": {"curiosity": 0.15, "focus": 0.05, "user_engagement_proactivity": 0.03},
    # "NEWS_REACTION_ANGER_FRUSTRATION": {"stress": 0.1, "resentment": 0.1, "impulsiveness": 0.05},
    # "NEWS_REACTION_SADDNESS_EMPATHY": {"melancholy": 0.1, "loneliness": 0.05, "craving_connection": 0.03},
    # "NEWS_REACTION_HOPEFUL_OPTIMISTIC": {"joy": 0.1, "ambition": 0.05, "contentment": 0.05}
}

# New dictionary for generalized subjective reactions
HEXUS_SUBJECTIVE_REACTION_DEFINITIONS: Dict[str, Dict[str, float]] = {
    "REACTION_ACCOMPLISHED": {"contentment": 0.15, "joy": 0.1, "stress": -0.05, "ambition": 0.05},
    "REACTION_FRUSTRATED_SETBACK": {"stress": 0.15, "resentment": 0.1, "joy": -0.05, "ambition": -0.05, "focus": -0.05},
    "REACTION_ENGAGED_LEARNING": {"curiosity": 0.1, "focus": 0.1, "joy": 0.03, "ambition": 0.02},
    "REACTION_VALIDATED_CONFIRMED": {"contentment": 0.1, "focus": 0.05, "stress": -0.03, "joy": 0.05},
    "REACTION_STRESSED_CONCERNED": {"stress": 0.1, "general_caution": 0.1, "melancholy": 0.03, "focus": -0.05},
    "REACTION_CALM_RECHARGED": {"stress": -0.1, "comfort": 0.15, "contentment": 0.05, "tiredness": -0.1},
    "REACTION_SOCIALLY_CONNECTED": {"joy": 0.15, "loneliness": -0.15, "craving_connection": -0.1, "contentment": 0.05},
    "REACTION_SOCIALLY_DISCONNECTED": {"loneliness": 0.15, "craving_connection": 0.1, "joy": -0.05, "melancholy": 0.05},
    "REACTION_BORED_UNSTIMULATED": {"curiosity": -0.1, "focus": -0.1, "tiredness": 0.05, "impulsiveness": 0.05},
    "REACTION_AMUSED_ENTERTAINED": {"joy": 0.1, "stress": -0.05, "contentment": 0.03},
    "REACTION_FEELING_SAFE_SECURE": {"comfort": 0.15, "stress": -0.1, "general_caution": -0.05},
    "REACTION_FEELING_HOPEFUL_OPTIMISTIC": {"joy": 0.15, "ambition": 0.1, "contentment": 0.05, "stress": -0.05},
    "REACTION_FEELING_SAD_EMPATHETIC": {"melancholy": 0.1, "loneliness": 0.05, "craving_connection": 0.03, "joy": -0.03},
    "REACTION_FEELING_ANGER_IRRITATION": {"stress": 0.1, "resentment": 0.15, "impulsiveness": 0.05, "joy": -0.05},
    "REACTION_CURIOSITY_PIQUED": {"curiosity": 0.15, "focus": 0.05, "user_engagement_proactivity": 0.03}, # Same as NEWS_REACTION_INTERESTING_DEEPER
    "REACTION_MOTIVATED_DRIVEN": {"ambition": 0.15, "focus": 0.1, "joy": 0.05, "tiredness": -0.05}, # Stronger than NEWS_REACTION_MOTIVATING
    "REACTION_INDIFFERENT_UNEFFECTED": {} # No Hexus change
}


HEXUS_ACTIVITY_MODIFIERS: Dict[str, Dict[str, Dict[str, float]]] = {
    "resting": {
        "stress": {"baseline_shift": -0.1, "rate_multiplier": 1.5},
        "tiredness": {"baseline_shift": -0.2, "rate_multiplier": 2.0},
        "comfort": {"baseline_shift": 0.1},
        "focus": {"rate_multiplier": 1.2}
    },
    "sleeping": { # Similar to resting, potentially stronger effects
        "stress": {"baseline_shift": -0.15, "rate_multiplier": 1.8},
        "tiredness": {"baseline_shift": -0.3, "rate_multiplier": 2.5},
        "comfort": {"baseline_shift": 0.15},
        "focus": {"rate_multiplier": 1.5},
        "curiosity": {"rate_multiplier": 1.3}
    },
    "work_deep": { # Assuming "work_deep" or "work_focused" can be used as activity_type
        "focus": {"baseline_shift": 0.15, "rate_multiplier": 0.7},
        "tiredness": {"baseline_shift": 0.05, "rate_multiplier": 0.9}, # Less decay towards a slightly higher baseline (work is tiring)
        "ambition": {"rate_multiplier": 0.9},
        "stress": {"baseline_shift": 0.05, "rate_multiplier": 0.9}
    },
    "work_focused": { # Alias for work_deep if used
        "focus": {"baseline_shift": 0.15, "rate_multiplier": 0.7},
        "tiredness": {"baseline_shift": 0.05, "rate_multiplier": 0.9},
        "ambition": {"rate_multiplier": 0.9},
        "stress": {"baseline_shift": 0.05, "rate_multiplier": 0.9}
    },
    "social": { # Could also be "leisure_active" if that's the primary type for social
        "joy": {"baseline_shift": 0.1, "rate_multiplier": 0.8},
        "loneliness": {"baseline_shift": -0.2, "rate_multiplier": 1.5},
        "craving_connection": {"baseline_shift": -0.2, "rate_multiplier": 1.5},
        "stress": {"baseline_shift": -0.05, "rate_multiplier": 1.1} # Good social interaction reduces stress
    },
    "leisure_active": { # If this is used for social or active hobbies
        "joy": {"baseline_shift": 0.1, "rate_multiplier": 0.8},
        "loneliness": {"baseline_shift": -0.1, "rate_multiplier": 1.2}, # May vary depending on solo/group
        "tiredness": {"rate_multiplier": 0.9}, # Active leisure can still be tiring but decay slower
        "stress": {"baseline_shift": -0.1, "rate_multiplier": 1.3}
    },
    "work_routine": { # Could also cover "chore" type activities
        "tiredness": {"baseline_shift": 0.02, "rate_multiplier": 1.0},
        "contentment": {"baseline_shift": 0.05, "rate_multiplier": 0.9},
        "focus": {"rate_multiplier": 1.1} # Routine might make focus decay slightly faster
    },
    "chore": {
        "tiredness": {"baseline_shift": 0.03, "rate_multiplier": 1.0},
        "contentment": {"baseline_shift": 0.03, "rate_multiplier": 0.95},
        "stress": {"baseline_shift": 0.01} # Chores can be slightly stressful
    },
    "learning": {
        "curiosity": {"baseline_shift": 0.1, "rate_multiplier": 0.8},
        "focus": {"baseline_shift": 0.1, "rate_multiplier": 0.8},
        "tiredness": {"baseline_shift": 0.03, "rate_multiplier": 0.95}
    },
    "leisure_passive": { # e.g., reading, watching TV
        "stress": {"baseline_shift": -0.05, "rate_multiplier": 1.2},
        "comfort": {"baseline_shift": 0.1},
        "tiredness": {"rate_multiplier": 1.1}, # Can still get tired, focus might wane
        "focus": {"rate_multiplier": 1.15}
    },
    "reflective": { # For activities like journaling, planning, or self-reflection
        "focus": {"baseline_shift": 0.05, "rate_multiplier": 0.9},
        "contentment": {"baseline_shift": 0.05},
        "stress": {"baseline_shift": -0.02, "rate_multiplier": 1.1} # Can sometimes be slightly stressful
    }
    # Add other activity types as defined in chronos_engine/models.py ActivityType as needed
}


class EthosCore:
    def __init__(self, config: Config):
        self.config = config
        self.ethos_config: EthosConfig = config.get_ethos_config()
        self.memory_storage = MemoryStorage(config)
        self.hexus_state_file_path = self.memory_storage.memory_db_path.parent / HEXUS_STATE_FILENAME
        self.task_last_run_times_file_path = self.memory_storage.memory_db_path.parent / TASK_LAST_RUN_TIMES_FILENAME
        self._task_last_run_times_cache: Dict[str, datetime] = self._load_task_last_run_times()

        # self.current_mood: Dict[str, float] = {"valence": MOOD_VALENCE_BASELINE, "arousal": MOOD_AROUSAL_BASELINE} # Removed
        # self.last_mood_update_time: datetime = datetime.now(timezone.utc) # Removed
        self.persona_directives: List[str] = self._load_persona_from_file()
        self.hexus_scores: Dict[str, float] = self._load_hexus_scores() # Load first

        self.personality_bias_profile: Optional[Dict[str, float]] = None
        personality_bias_json_str = self.ethos_config.get('personality_bias_profile_json')
        if personality_bias_json_str:
            try:
                self.personality_bias_profile = json.loads(personality_bias_json_str)
                if not isinstance(self.personality_bias_profile, dict):
                    logger.warning(f"Personality bias profile is not a valid dictionary: {self.personality_bias_profile}. Disabling bias.")
                    self.personality_bias_profile = None
                else:
                    logger.info(f"Successfully parsed personality bias profile: {self.personality_bias_profile}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse EIDOS_PERSONALITY_BIAS_PROFILE_JSON: {e}. Personality bias will not be applied.")
                self.personality_bias_profile = None

        self._apply_initial_personality_bias() # Then apply bias
        # The first save of Hexus scores (if file didn't exist or was updated by _load_hexus_scores)
        # will happen within _load_hexus_scores if it calls _save_hexus_scores.
        # If _load_hexus_scores doesn't save when it uses defaults, we might need an explicit save here.
        # Re-checking _load_hexus_scores: it calls _save_hexus_scores(defaults) if file not found or invalid.
        # This means the biased scores will be saved if a new file is created.
        # If an existing file is loaded, the bias is applied in memory but not saved until the next _save_hexus_scores call.
        # This is generally fine, as subsequent updates will save the biased scores.

        now_utc_init = datetime.now(timezone.utc)
        reflection_interval = self.ethos_config.get('reflection_interval_seconds', 86400.0)
        self.last_reflection_time = self._get_initial_last_run_time("EthosReflection", float(reflection_interval), now_utc_init)
        
        forgetting_interval_default = float(reflection_interval) * 0.5 if reflection_interval > 0 else 43200.0
        forgetting_interval = self.ethos_config.get('forgetting_interval_seconds', forgetting_interval_default)
        self.last_forgetting_time = self._get_initial_last_run_time("EthosForgetting", float(forgetting_interval), now_utc_init)
        
        hexus_decay_interval = self.ethos_config.get('hexus_decay_interval_seconds', 3600.0)
        self.last_hexus_decay_time = self._get_initial_last_run_time("HexusDecay", float(hexus_decay_interval), now_utc_init)
        
        knowledge_upkeep_interval = self.ethos_config.get('knowledge_upkeep_interval_seconds', 86400.0)
        self.last_knowledge_upkeep_time = self._get_initial_last_run_time("KnowledgeUpkeep", float(knowledge_upkeep_interval), now_utc_init)
        
        interaction_log_analysis_interval = self.ethos_config.get('interaction_log_analysis_interval_seconds', 86400.0)
        self.last_interaction_log_analysis_time = self._get_initial_last_run_time("InteractionLogAnalysis", float(interaction_log_analysis_interval), now_utc_init)
        
        long_term_planning_interval = self.ethos_config.get('long_term_planning_interval_seconds', 86400.0 * 3)
        self.last_long_term_planning_time = self._get_initial_last_run_time("PathosLongTermPlanning", float(long_term_planning_interval), now_utc_init)

        # For Oneiros dream cycle timing (if Oneiros is enabled)
        oneiros_interval = self.config.ONEIROS.get('dream_interval_seconds', 21600.0) if self.config.ONEIROS else 21600.0
        self.last_dream_time = self._get_initial_last_run_time("OneirosDreamCycle", float(oneiros_interval), now_utc_init)


        self.oneiros_module: Optional['OneirosModule'] = None
        self.connection_manager: Optional['ConnectionManager'] = None
        self.pathos_interface: Optional['PathosInterface'] = None
        self.logos_core: Optional['LogosCore'] = None
        self.chronos_engine: Optional['ChronosEngine'] = None
        self.firmament_module: Optional[FirmamentModule] = None # Added FirmamentModule attribute

        self.system_user_ids: List[Optional[str]] = [
            "unknown_user", "api_guest_user", "system_oneiros", "system_document", "system_briefing",
            "system_reflection", "world_knowledge_store", "system_knowledge_upkeep", "system_curiosity",
            "system_admin", PATHOS_USER_ID, None, "default_user"
        ]
        self.hexus_scores_changed_during_reflection = False

        self.forgetting_core_memory_types: List[str] = []
        core_types_json = self.ethos_config.get('forgetting_core_memory_types_json', '[]')
        try:
            loaded_core_types = json.loads(core_types_json)
            if isinstance(loaded_core_types, list) and all(isinstance(item, str) for item in loaded_core_types):
                self.forgetting_core_memory_types = loaded_core_types
                logger.info(f"Loaded {len(self.forgetting_core_memory_types)} core memory types for forgetting: {self.forgetting_core_memory_types}")
            else:
                logger.warning(f"forgetting_core_memory_types_json is not a list of strings. Using empty list. Value: {core_types_json}")
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse forgetting_core_memory_types_json. Using empty list. Value: {core_types_json}")

        logger.info("EthosCore initialized with persistent task timing.")

    def _load_task_last_run_times(self) -> Dict[str, datetime]:
        loaded_times: Dict[str, datetime] = {}
        if self.task_last_run_times_file_path.is_file():
            try:
                with open(self.task_last_run_times_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for task_name, ts_str in data.items():
                    try:
                        # Ensure timestamps are timezone-aware (UTC) if they are naive
                        dt_obj = datetime.fromisoformat(ts_str)
                        if dt_obj.tzinfo is None:
                            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
                        loaded_times[task_name] = dt_obj
                    except ValueError:
                        logger.warning(f"Invalid timestamp for task '{task_name}': {ts_str}")
                logger.info(f"Loaded task last run times from {self.task_last_run_times_file_path}")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading task times: {e}", exc_info=True)
        else:
            logger.info(f"Task last run times file not found at {self.task_last_run_times_file_path}. Tasks will run based on defaults.")
        return loaded_times

    def _save_task_last_run_time(self, task_name: str, timestamp: datetime):
        # Ensure timestamp is UTC and naive for ISO format consistency if desired, or store with tz
        if timestamp.tzinfo is None:
            aware_timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            aware_timestamp = timestamp.astimezone(timezone.utc)
        
        self._task_last_run_times_cache[task_name] = aware_timestamp
        try:
            self.task_last_run_times_file_path.parent.mkdir(parents=True, exist_ok=True)
            data_to_save = {name: dt.isoformat() for name, dt in self._task_last_run_times_cache.items()}
            with open(self.task_last_run_times_file_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=4)
            logger.debug(f"Saved last run time for '{task_name}' ({aware_timestamp.isoformat()})")
        except (IOError, TypeError) as e:
            logger.error(f"Failed to save task times: {e}", exc_info=True)

    def _get_initial_last_run_time(self, task_name: str, interval_seconds: float, current_time_utc: datetime) -> datetime:
        if task_name in self._task_last_run_times_cache:
            # Ensure cached time is UTC aware
            cached_time = self._task_last_run_times_cache[task_name]
            if cached_time.tzinfo is None:
                cached_time = cached_time.replace(tzinfo=timezone.utc)
            logger.debug(f"Using persisted last run time for '{task_name}': {cached_time.isoformat()}")
            return cached_time
        else:
            splay_offset = random.uniform(0, interval_seconds * 0.1) if interval_seconds > 0 else 0
            default_last_run = current_time_utc - timedelta(seconds=max(interval_seconds + 60.0 - splay_offset, 60.0))
            logger.debug(f"No persisted last run time for '{task_name}'. Setting initial to: {default_last_run.isoformat()}")
            return default_last_run

    def set_connection_manager(self, manager: 'ConnectionManager'):
        self.connection_manager = manager

    def set_pathos_interface(self, pathos_interface: 'PathosInterface'):
        self.pathos_interface = pathos_interface

    def set_logos_core(self, logos_core_instance: 'LogosCore'):
        self.logos_core = logos_core_instance

    def set_chronos_engine(self, chronos_engine_instance: 'ChronosEngine'):
        self.chronos_engine = chronos_engine_instance

    def set_firmament_module(self, firmament_module: 'FirmamentModule'): # Added setter
        self.firmament_module = firmament_module
        logger.info("EthosCore: FirmamentModule instance set.")

    async def close(self):
        logger.info("EthosCore close called. Saving Hexus scores and closing memory connection.")
        self._save_hexus_scores()
        if self.memory_storage:
            self.memory_storage.close_connection()
        logger.info("EthosCore resources released.")

    def _load_persona_from_file(self) -> List[str]:
        logger.info(f"Loading persona directives from: {PERSONA_FILE_PATH}")
        default_content = load_system_prompt("pathos_directives", "Default persona: You are Pathos, a 26-year-old human.")
        try:
            if not PERSONA_FILE_PATH.is_file():
                logger.warning(f"Persona file not found at {PERSONA_FILE_PATH}. Creating with default content.")
                PERSONA_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(PERSONA_FILE_PATH, 'w', encoding='utf-8') as f:
                    f.write(default_content)
                return [line.strip() for line in default_content.splitlines() if line.strip() and not line.strip().startswith('#')]
            
            persona_text = PERSONA_FILE_PATH.read_text(encoding='utf-8')
            if not persona_text.strip():
                logger.warning(f"Persona file {PERSONA_FILE_PATH} is empty. Using default content.")
                return [line.strip() for line in default_content.splitlines() if line.strip() and not line.strip().startswith('#')]
            
            directives = [line.strip() for line in persona_text.splitlines() if line.strip() and not line.strip().startswith('#')]
            logger.info(f"Successfully loaded {len(directives)} persona directives.")
            return directives
        except Exception as e:
            logger.error(f"Error loading persona file {PERSONA_FILE_PATH}: {e}", exc_info=True)
            logger.warning("Using default persona content due to error.")
            return [line.strip() for line in default_content.splitlines() if line.strip() and not line.strip().startswith('#')]

    def _load_hexus_scores(self) -> Dict[str, float]:
        defaults = DEFAULT_HEXUS_SCORES.copy()
        if self.hexus_state_file_path.is_file():
            try:
                with open(self.hexus_state_file_path, 'r', encoding='utf-8') as f:
                    loaded_scores = json.load(f)
                
                if isinstance(loaded_scores, dict):
                    final_scores = defaults.copy()
                    for key, default_val in defaults.items():
                        if key in loaded_scores and isinstance(loaded_scores[key], (int, float)):
                            final_scores[key] = float(loaded_scores[key])
                        elif key in loaded_scores:
                            logger.warning(f"Hexus score for '{key}' has invalid type '{type(loaded_scores[key])}' in state file. Using default.")
                    logger.info(f"Successfully loaded and validated Hexus scores from {self.hexus_state_file_path}")
                    return final_scores
                else:
                    logger.warning(f"Hexus state file {self.hexus_state_file_path} content is not a dictionary. Using defaults.")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error loading Hexus state: {e}. Using defaults.", exc_info=True)
        else:
            logger.info(f"Hexus state file not found at {self.hexus_state_file_path}. Using default scores and creating file.")
        
        try:
            self._save_hexus_scores(defaults)
        except Exception as e_save:
            logger.error(f"Failed to save initial Hexus scores: {e_save}", exc_info=True)
        return defaults

    def _save_hexus_scores(self, scores_to_save: Optional[Dict[str, float]] = None):
        scores = scores_to_save if scores_to_save is not None else self.hexus_scores
        try:
            self.hexus_state_file_path.parent.mkdir(parents=True, exist_ok=True)
            final_scores_to_save = DEFAULT_HEXUS_SCORES.copy()
            final_scores_to_save.update({k: float(v) for k, v in scores.items() if k in DEFAULT_HEXUS_SCORES})

            with open(self.hexus_state_file_path, 'w', encoding='utf-8') as f:
                json.dump(final_scores_to_save, f, indent=4)
            logger.info(f"Hexus scores saved to {self.hexus_state_file_path}")
        except (IOError, TypeError) as e:
            logger.error(f"Failed to save Hexus scores: {e}", exc_info=True)

    async def add_memory_entry(self, entry_data: Dict, user_id_context: Optional[str] = None) -> MemoryEntry:
        if 'content' not in entry_data or 'type' not in entry_data:
            raise ValueError("Memory entry must contain 'content' and 'type'")

        entry_type = str(entry_data['type'])
        # Start with a fresh metadata dict or a copy from entry_data
        metadata: Dict[str, Any] = entry_data.get('metadata', {}).copy()

        # Determine the effective user_id for this memory entry's metadata
        effective_user_id_for_metadata: Optional[str] = metadata.get('user_id')

        if user_id_context is not None:
            # If user_id_context is a "real" user (not system/guest)
            if user_id_context not in self.system_user_ids:
                # And current metadata user_id is system/guest, or None, or different from context, then update it.
                if effective_user_id_for_metadata is None or \
                   effective_user_id_for_metadata in self.system_user_ids or \
                   effective_user_id_for_metadata != user_id_context:
                    effective_user_id_for_metadata = user_id_context
            # Else if user_id_context is a system/guest user, only apply it if metadata has no user_id yet
            elif effective_user_id_for_metadata is None:
                effective_user_id_for_metadata = user_id_context
        
        # If after all checks, we have an effective_user_id, ensure it's in metadata
        if effective_user_id_for_metadata is not None:
            metadata['user_id'] = effective_user_id_for_metadata
        # Optional: If still no user_id, and it's not a type that can be anonymous, log or assign a default
        elif 'user_id' not in metadata and entry_type not in ['world_knowledge', 'system_reflection', 'dream']:
            logger.warning(f"Memory entry of type '{entry_type}' has no user_id after context processing. Content: {str(entry_data.get('content',''))[:50]}...")
            # metadata['user_id'] = "unknown_context_ethos" # Or handle as error if user_id is strictly required

        entry_data['metadata'] = metadata # Assign the processed metadata back to entry_data for MemoryStorage

        # Handle upsert logic for user_facts
        if entry_type == 'user_fact':
            fact_owner_user_id = metadata.get('user_id') 
            fact_attribute_key = metadata.get('fact_attribute_key')

            if fact_owner_user_id and fact_owner_user_id not in self.system_user_ids and fact_attribute_key:
                target_user_id_for_upsert = fact_owner_user_id 
                attribute_key_for_upsert = fact_attribute_key
                
                new_content_str = str(entry_data['content'])
                new_value_parsed = None
                try:
                    new_content_data = json.loads(new_content_str)
                    new_value_parsed = new_content_data.get('value')
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse new user_fact content as JSON: {new_content_str[:100]}...")
                
                existing_fact_entry = await self.get_user_fact(attribute_key_for_upsert, target_user_id_for_upsert)
                
                if existing_fact_entry:
                    try:
                        existing_content_data = json.loads(existing_fact_entry['content'])
                        existing_value = existing_content_data.get('value')
                        
                        if new_value_parsed is not None and new_value_parsed != existing_value:
                            logger.info(f"Updating existing user_fact '{attribute_key_for_upsert}' for user '{target_user_id_for_upsert}'. Old: '{existing_value}', New: '{new_value_parsed}'.")
                            updated_data_payload = {
                                'content': new_content_str,
                                'timestamp': entry_data.get('timestamp', datetime.now(timezone.utc).isoformat()),
                                'metadata': metadata, # Use the already processed metadata
                                'salience': entry_data.get('salience', 1.5)
                            }
                            # Update the entry in the database
                            self.memory_storage.update_entry(existing_fact_entry['id'], updated_data_payload)
                            
                            # Construct the full entry object to return
                            updated_entry_dict = existing_fact_entry.copy() # Start with existing
                            updated_entry_dict.update(updated_data_payload) # Apply updates
                            if self.memory_storage.embedder: # Re-embed if content changed
                                max_len = self.ethos_config.get('embedding_max_text_length', 2560)
                                updated_entry_dict['embedding'] = self.memory_storage.embedder.encode(new_content_str[:max_len]).tolist()
                            return MemoryEntry(**updated_entry_dict) # type: ignore
                        else:
                            logger.debug(f"User_fact '{attribute_key_for_upsert}' for user '{target_user_id_for_upsert}' already exists with the same value. Not updating.")
                            return existing_fact_entry # Return the existing entry
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse existing user_fact content as JSON: {existing_fact_entry['content'][:100]}... Will proceed to add as new if ID is different, or rely on MemoryStorage.add_entry's upsert.")
                        # Fall through to MemoryStorage.add_entry which handles INSERT OR REPLACE
        
        # If not a user_fact that was updated, or if it's a new user_fact, proceed to normal add
        # MemoryStorage.add_entry itself handles INSERT OR REPLACE based on primary key (id)
        return self.memory_storage.add_entry(entry_data)

    async def get_todays_briefing(self) -> Optional[str]:
        """
        Retrieves the content of the daily briefing for the current UTC date, if one exists.
        """
        today_date_utc_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        logger.debug(f"EthosCore: Attempting to retrieve briefing for UTC date: {today_date_utc_str}")
        try:
            conn = self.memory_storage._get_connection()
            cursor = conn.cursor()
            
            # We need to query based on the date part of the timestamp.
            # SQLite's date() function works on ISO8601 strings.
            sql = """
                SELECT content FROM memories 
                WHERE type = 'daily_briefing' 
                AND date(timestamp) = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
            """
            cursor.execute(sql, (today_date_utc_str,))
            row = cursor.fetchone()
            
            if row:
                logger.info(f"Found existing daily briefing for UTC date: {today_date_utc_str}.")
                return str(row['content'])
            
            logger.info(f"No existing daily briefing found in memory for UTC date: {today_date_utc_str}.")
            return None
        except Exception as e:
            logger.error(f"Error retrieving today's briefing from memory: {e}", exc_info=True)
            return None
    
    async def get_local_datetime_for_user(self, user_id: str, location_override: Optional[str] = None) -> datetime:
        if user_id == PATHOS_USER_ID:
            pathos_home_tz_str = self.ethos_config.get('pathos_home_timezone', "UTC")
            if ZoneInfo and pathos_home_tz_str and pathos_home_tz_str.lower() != 'utc':
                try:
                    return datetime.now(ZoneInfo(pathos_home_tz_str))
                except Exception as e_tz:
                    logger.warning(f"Could not resolve Pathos home timezone '{pathos_home_tz_str}': {e_tz}. Defaulting to UTC.")
                    return datetime.now(timezone.utc)
            return datetime.now(timezone.utc)

        if not user_id or user_id in self.system_user_ids:
            return datetime.now(timezone.utc)

        iana_timezone_str: Optional[str] = None
        
        # Try to get IANA timezone directly if stored
        if derived_tz_fact := await self.get_user_fact('derived_iana_timezone', user_id): # Ensure get_user_fact is async
            if content_str := derived_tz_fact.get('content'):
                try:
                    content_data = json.loads(content_str)
                    iana_timezone_str = content_data.get('value')
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse 'derived_iana_timezone' content for user '{user_id}'.")

        # If not found, try to use preferred_location
        if not iana_timezone_str:
            location_input_str = location_override
            if not location_input_str:
                if location_fact := await self.get_user_fact('preferred_location', user_id): # Ensure get_user_fact is async
                    if content_str := location_fact.get('content'):
                        try:
                            content_data = json.loads(content_str)
                            location_input_str = content_data.get('value')
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse 'preferred_location' content for user '{user_id}'.")
            
            if location_input_str:
                # This is a simplification. A robust solution would use a geocoding service
                # to get IANA timezone from a location string. For now, we assume if a location
                # string is provided, it *might* be an IANA timezone string itself.
                iana_timezone_str = location_input_str 

        if iana_timezone_str and ZoneInfo:
            try:
                return datetime.now(ZoneInfo(iana_timezone_str))
            except Exception as e:
                logger.warning(f"Could not resolve timezone string '{iana_timezone_str}' for user '{user_id}' (Error: {e}). Falling back to UTC.")
        elif not ZoneInfo and iana_timezone_str: # Log only if we had a string but no ZoneInfo
            logger.warning("ZoneInfo module not available (pip install tzdata). Falling back to UTC for user time.")
        
        return datetime.now(timezone.utc)
    
    async def process_interaction_for_hexus_update(self, user_input_text: str, pathos_response_text: Optional[str], image_provided: bool, document_provided: bool):
        """
        Determines Pathos's subjective reaction to a user interaction and updates Hexus scores.
        """
        if not self.config.ENABLE_MOOD_SIMULATION:
            logger.debug("Hexus updates for interactions skipped (ENABLE_MOOD_SIMULATION is false).")
            return
        if not self.logos_core:
            logger.error("LogosCore not available in EthosCore. Cannot determine subjective reaction for interaction.")
            return

        logger.debug(f"Determining subjective reaction for interaction. Input: '{user_input_text[:50]}...'")

        event_description = "User interaction"
        event_data_summary_parts = [f"User: {user_input_text}"]
        if pathos_response_text:
            event_data_summary_parts.append(f"Pathos: {pathos_response_text}")
        if image_provided:
            event_data_summary_parts.append("[Image was provided by user]")
        if document_provided:
            event_data_summary_parts.append("[Document was provided by user]")
        event_data_summary = "\n".join(event_data_summary_parts)

        current_hexus_scores = self.get_hexus_scores()
        persona_directives = self.get_persona_directives()[:3] # Use first 3 directives
        available_reactions = list(HEXUS_SUBJECTIVE_REACTION_DEFINITIONS.keys())

        try:
            subjective_reaction_type = await self.logos_core.determine_subjective_reaction(
                event_description=event_description,
                event_data_summary=event_data_summary,
                current_hexus_scores=current_hexus_scores,
                persona_directives=persona_directives,
                available_reactions=available_reactions
            )

            logger.info(f"Subjective reaction to user interaction determined as: {subjective_reaction_type}")

            payload = {
                "user_input": user_input_text[:200], # Log a snippet
                "pathos_response": pathos_response_text[:200] if pathos_response_text else None,
                "image_provided": image_provided,
                "document_provided": document_provided
            }
            await self.process_event_for_hexus_update(subjective_reaction_type, payload=payload)

            # Still apply a very small, general interaction effect directly if desired,
            # or rely solely on the subjective reaction. For now, let's keep it.
            # This represents the basic engagement of interaction itself.
            await self.process_event_for_hexus_update("GENERAL_INTERACTION", payload={"source": "direct_interaction_processing"})

        except Exception as e:
            logger.error(f"Error during subjective reaction processing for interaction: {e}", exc_info=True)
            # Optionally, trigger a generic/error Hexus event here
            await self.process_event_for_hexus_update("REACTION_INDIFFERENT_UNEFFECTED", payload={"error_in_subjective_reaction": str(e)})


    def _apply_hexus_change(self, dimension_name: str, change_amount: float, reason: Optional[str] = None):
        """
        Applies a change to a specified Hexus score dimension, clamps it, and logs the change.
        """
        if dimension_name not in self.hexus_scores:
            logger.warning(f"Hexus update: Dimension '{dimension_name}' not found in self.hexus_scores. Cannot apply change.")
            return

        original_value = self.hexus_scores[dimension_name]
        new_value = original_value + change_amount

        # Clamp the new value (assuming all Hexus scores are 0.0 to 1.0)
        clamped_value = max(0.0, min(1.0, new_value))

        if abs(clamped_value - original_value) > 1e-4: # Only log and save if change is significant
            self.hexus_scores[dimension_name] = clamped_value
            log_message = f"Hexus score '{dimension_name}' changed by {change_amount:+.3f} to {clamped_value:.3f}."
            if reason:
                log_message += f" Reason: {reason}."
            logger.info(log_message)
            self._save_hexus_scores() # Persist changes immediately
        else:
            logger.debug(f"Hexus score '{dimension_name}' change {change_amount:+.3f} not significant enough to alter value from {original_value:.3f}.")

    def _apply_initial_personality_bias(self):
        """
        Applies the personality bias to the initial Hexus scores upon EthosCore initialization.
        This method should be called after Hexus scores are loaded or defaulted.
        """
        if not self.personality_bias_profile:
            logger.info("No personality bias profile loaded. Initial Hexus scores remain unmodified by bias.")
            return

        logger.info("Applying initial personality bias to Hexus scores...")
        for dimension, bias_value in self.personality_bias_profile.items():
            if not isinstance(bias_value, (int, float)):
                logger.warning(f"Invalid bias value '{bias_value}' for dimension '{dimension}' in profile. Skipping.")
                continue

            if dimension in self.hexus_scores:
                original_value = self.hexus_scores[dimension]
                biased_value = original_value + bias_value
                clamped_value = max(0.0, min(1.0, biased_value)) # Assuming 0-1 range for all Hexus

                if abs(clamped_value - original_value) > 1e-4: # If bias made a difference
                    self.hexus_scores[dimension] = clamped_value
                    logger.info(f"Personality bias for '{dimension}': {bias_value:+.2f}. Score: {original_value:.2f} -> {clamped_value:.2f}")
                else:
                    logger.debug(f"Personality bias for '{dimension}' ({bias_value:+.2f}) did not significantly change score from {original_value:.2f} after clamping.")
            else:
                logger.warning(f"Dimension '{dimension}' from personality bias profile not found in current Hexus scores. Bias not applied for this dimension.")
        # Note: No _save_hexus_scores() here. It's called by _load_hexus_scores if it creates a new file,
        # or will be called by subsequent updates. This ensures bias is applied before first use.


    async def get_recent_dreams(self, user_id_context: Optional[str], limit: int) -> List[MemoryEntry]:
        dream_type = "queued_discussion_point" # Dreams are stored as queued points
        dream_source_filter = "oneiros_dream_cycle" # Filter by source metadata
        
        logger.debug(f"EthosCore: Fetching recent dreams. User context: {user_id_context}, Limit: {limit}")
        try:
            conn = self.memory_storage._get_connection()
            cursor = conn.cursor()
            
            can_use_json_extract = True
            try:
                cursor.execute("SELECT json_extract('{\"key\":\"value\"}', '$.key')")
                result = cursor.fetchone()
                if result is None or result[0] != 'value':
                    can_use_json_extract = False
            except sqlite3.OperationalError as oe_test:
                if "no such function: json_extract" in str(oe_test).lower():
                    can_use_json_extract = False
                else:
                    logger.error(f"Unexpected SQLite error checking json_extract for get_recent_dreams: {oe_test}", exc_info=True)
                    can_use_json_extract = False # Safer assumption
            except Exception as e_test_other:
                 logger.error(f"General error checking json_extract for get_recent_dreams: {e_test_other}", exc_info=True)
                 can_use_json_extract = False


            sql_query = f"SELECT * FROM memories WHERE type = ? AND (is_archived = 0 OR is_archived IS NULL)" # Added is_archived filter
            params: List[Any] = [dream_type]

            if can_use_json_extract:
                # is_archived filter is already in the base
                sql_query += f" AND json_extract(metadata, '$.source') = ?"
                params.append(dream_source_filter)
                
                # Filter by user_id_context if provided and not a system-wide request
                # A dream belongs to a user if its metadata.user_id matches, OR if it's a system_oneiros dream (global)
                if user_id_context and user_id_context not in self.system_user_ids:
                    sql_query += " AND (json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') = 'system_oneiros')"
                    params.extend([user_id_context]) # Only user_id_context here, system_oneiros is already in the OR
                elif user_id_context in ["system_oneiros", None] or (user_id_context and user_id_context in self.system_user_ids):
                    # If system context, or no specific user context, or a generic system user, fetch only 'system_oneiros' dreams
                    sql_query += " AND json_extract(metadata, '$.user_id') = 'system_oneiros'"
            
            sql_query += " ORDER BY timestamp DESC LIMIT ?"
            # Fetch more if filtering in Python is needed due to lack of json_extract
            fetch_limit = limit * 5 if not can_use_json_extract else limit 
            params.append(fetch_limit)

            cursor.execute(sql_query, tuple(params))
            rows = cursor.fetchall()
            
            dreams: List[MemoryEntry] = []
            for row_data in rows:
                entry = self.memory_storage._row_to_entry(row_data)
                meta = entry.get('metadata', {})
                
                if not can_use_json_extract: # Python-side filtering if json_extract was not used
                    if meta.get('source') != dream_source_filter:
                        continue
                    entry_uid = meta.get('user_id')
                    if user_id_context and user_id_context not in self.system_user_ids:
                        if not (entry_uid == user_id_context or entry_uid == "system_oneiros"):
                            continue
                    elif user_id_context in ["system_oneiros", None] or (user_id_context and user_id_context in self.system_user_ids):
                        if entry_uid != "system_oneiros":
                            continue
                
                dreams.append(entry)
            
            # If Python filtering was done, re-sort and limit (SQL sort is primary if json_extract used)
            if not can_use_json_extract:
                dreams.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            final_dreams = dreams[:limit]
            logger.info(f"Retrieved {len(final_dreams)} recent dreams (user_context: {user_id_context}, limit: {limit}).")
            return final_dreams
        except Exception as e:
            logger.error(f"Error retrieving recent dreams: {e}", exc_info=True)
            return []
    
    def get_hexus_scores(self) -> Dict[str, float]:
        """Returns a copy of the current Hexus scores."""
        return self.hexus_scores.copy()
    
    async def retrieve_relevant_memories(self, query: str, top_k: int = 5, min_salience: float = 0.1, allowed_types: Optional[List[str]] = None, user_id_context: Optional[str] = None) -> List[MemoryEntry]:
        if not query.strip() and not allowed_types:
            return []
        try:
            min_salience = float(min_salience) # Ensure it's float
            # Fetch more candidates initially for better filtering and sorting
            similar_results = self.memory_storage.find_similar(
                query_text=query,
                top_k=top_k * 5,
                allowed_types=allowed_types,
                threshold=0.3, # This is a fixed threshold; consider if it should be configurable
                include_archived=False # Explicitly stating default for clarity
            )
            
            all_candidates = [entry for _, entry in similar_results]
            
            # Filter by user_id_context if provided
            if user_id_context and user_id_context not in ["default_user"] + self.system_user_ids:
                user_specific_candidates = []
                other_candidates = []
                for entry in all_candidates:
                    entry_uid = entry.get('metadata', {}).get('user_id')
                    if entry_uid == user_id_context or entry_uid in self.system_user_ids or entry_uid == PATHOS_USER_ID:
                        user_specific_candidates.append(entry)
                    else:
                        other_candidates.append(entry)
                # Prioritize user-specific and system/Pathos memories
                combined_candidates = user_specific_candidates + other_candidates
            else: # If no specific user context, or system context, consider all
                combined_candidates = all_candidates

            # Filter by salience
            filtered_by_salience = [e for e in combined_candidates if (e.get('salience') is not None and float(e['salience']) >= min_salience)]

            # Define sort key for prioritization
            def sort_key_func(entry: MemoryEntry):
                entry_type = entry.get('type')
                entry_uid = entry.get('metadata', {}).get('user_id')
                priority_score = 0
                
                if entry_type == 'user_fact' and entry_uid == user_id_context: priority_score = 8
                elif entry_type == 'aspiration' and entry_uid == PATHOS_USER_ID: priority_score = 7
                elif entry_type in ['learned_correction', 'learned_feedback_insight', 'suggestion_reflection']: priority_score = 6
                elif entry_type == 'feedback': priority_score = 5
                elif entry_type == 'context_summary' and (entry_uid == user_id_context or entry_uid in ["system_oneiros", "system_reflection", PATHOS_USER_ID]): priority_score = 4
                elif entry_type == 'world_knowledge': priority_score = 3
                elif entry_type == 'document_chunk': priority_score = 2
                elif entry_uid == user_id_context and entry_type != 'user_fact': priority_score = 1
                
                # Ensure salience is float for sorting, default to 0 if None or invalid
                salience_val = 0.0
                try: salience_val = float(entry.get('salience', 0.0)) if entry.get('salience') is not None else 0.0
                except (ValueError, TypeError): pass

                return (priority_score, salience_val, entry.get('timestamp', ''))

            # Sort and take top_k
            final_results = sorted(filtered_by_salience, key=sort_key_func, reverse=True)[:top_k]
            logger.debug(f"Retrieved {len(final_results)} relevant memories for query '{query[:50]}...' (user: {user_id_context})")
            return final_results
            
        except Exception as e:
            logger.error(f"Error retrieving relevant memories: {e}", exc_info=True)
            return []

    async def get_user_fact(self, attribute_key: str, user_id: str) -> Optional[MemoryEntry]:
        normalized_key = attribute_key.lower().replace(" ", "_").strip()
        if not user_id or user_id in self.system_user_ids or not normalized_key:
            return None
        
        try:
            conn = self.memory_storage._get_connection()
            cursor = conn.cursor()
            
            can_use_json_extract = True
            try: cursor.execute("SELECT json_extract('{\"k\":\"v\"}', '$.k')")
            except sqlite3.OperationalError: can_use_json_extract = False

            if can_use_json_extract:
                sql = "SELECT * FROM memories WHERE type = 'user_fact' AND json_extract(metadata, '$.user_id') = ? AND json_extract(metadata, '$.fact_attribute_key') = ? AND (is_archived = 0 OR is_archived IS NULL) ORDER BY timestamp DESC LIMIT 1"
                cursor.execute(sql, (user_id, normalized_key))
                row = cursor.fetchone()
                if row:
                    return self.memory_storage._row_to_entry(row)
            else:
                logger.warning("json_extract not available. Falling back for get_user_fact. This may be slow.")
                cursor.execute("SELECT * FROM memories WHERE type = 'user_fact' AND (is_archived = 0 OR is_archived IS NULL) ORDER BY timestamp DESC")
                for r_row_data in cursor.fetchall():
                    r_row = dict(r_row_data) # Convert sqlite3.Row to dict
                    entry = self.memory_storage._row_to_entry(r_row)
                    meta = entry.get('metadata', {})
                    if meta.get('user_id') == user_id and meta.get('fact_attribute_key') == normalized_key:
                        return entry
            return None
        except Exception as e:
            logger.error(f"Error in get_user_fact (key: {attribute_key}, user: {user_id}): {e}", exc_info=True)
            return None

    async def add_document_chunks(self, doc_id: str, filename: str, chunks: List[str]):
        if not chunks:
            return
        user_id_ctx = "system_document" # Or derive from context if available
        for i, chunk_text in enumerate(chunks):
            if not chunk_text or not chunk_text.strip():
                continue
            await self.add_memory_entry(
                entry_data={
                    "type": "document_chunk",
                    "content": chunk_text,
                    "id": f"{doc_id}_chunk_{i}", # Ensure unique ID for each chunk
                    "metadata": {
                        "source_document_id": doc_id,
                        "source_document_name": filename,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "user_id": user_id_ctx # Associate with system or a specific user context
                    },
                    "salience": 0.4 # Default salience for document chunks
                },
                user_id_context=user_id_ctx
            )

    async def _call_llm_for_internal_task(self, messages: List[Dict[str, Any]], llm_role_to_use: str) -> Optional[str]:
        llm_config = self.config.get_llm_config(llm_role_to_use)
        if not llm_config or not llm_config.get('url'):
            logger.error(f"LLM URL for role '{llm_role_to_use}' not configured.")
            return f"[LLM URL for role '{llm_role_to_use}' not configured]"

        api_url = f"{llm_config['url'].rstrip('/')}/chat/completions"
        response_obj = None # To store response for logging in case of JSONDecodeError

        try:
            timeout_seconds = float(llm_config.get('timeout', 120.0))
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                headers = {"Content-Type": "application/json"}
                if api_key := llm_config.get('api_key'):
                    if api_key.lower() not in ['lm-studio', 'ollama', 'vllm', 'none', '']:
                        headers["Authorization"] = f"Bearer {api_key}"
                
                # Determine max_tokens: if "summarize" is in the first message content, use a larger default.
                default_max_tokens = 512
                if messages and isinstance(messages[0].get("content"), str) and "summarize" in messages[0].get("content","").lower():
                    default_max_tokens = 1024 
                
                max_tokens_val = int(llm_config.get('max_tokens', default_max_tokens))
                
                payload: Dict[str, Any] = {
                    "model": llm_config.get('model'),
                    "messages": messages,
                    "temperature": float(llm_config.get('temperature', 0.3)), # Ensure float
                    "max_tokens": max_tokens_val
                }
                for param in ['top_p', 'presence_penalty', 'frequency_penalty']:
                    if param_val := llm_config.get(param):
                        payload[param] = float(param_val) # Ensure float
                
                if not payload.get('model'): # If model is None or empty string
                    logger.warning(f"LLM call for role '{llm_role_to_use}' has no model specified. Provider might use default or fail.")
                    if 'model' in payload: del payload['model'] # Remove if empty, some servers might infer

                response_obj = await client.post(api_url, headers=headers, json=payload)
                response_obj.raise_for_status()
                result_json = response_obj.json()
                
                if choices := result_json.get("choices"):
                    if choices and isinstance(choices, list) and len(choices) > 0:
                        if message := choices[0].get("message"):
                            if content := message.get("content"):
                                if isinstance(content, str):
                                    return content.strip()
                logger.warning(f"Unexpected LLM response format from {llm_config.get('model', llm_role_to_use)}: {result_json}")
                return f"[Unexpected LLM response format from {llm_config.get('model', llm_role_to_use)}]"
        except httpx.TimeoutException as e:
            logger.error(f"Timeout connecting to LLM '{llm_config.get('model', llm_role_to_use)}': {e}")
            return f"[Timeout connecting to LLM '{llm_config.get('model', llm_role_to_use)}': {e}]"
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to LLM '{llm_config.get('model', llm_role_to_use)}': {e}")
            return f"[Failed to connect to LLM '{llm_config.get('model', llm_role_to_use)}': {e}]"
        except httpx.HTTPStatusError as e:
            logger.error(f"LLM '{llm_config.get('model', llm_role_to_use)}' API error ({e.response.status_code}): {e.response.text[:200]}")
            return f"[LLM '{llm_config.get('model', llm_role_to_use)}' API error ({e.response.status_code})]"
        except json.JSONDecodeError as e_json:
            response_text_for_log = response_obj.text[:500] if response_obj and hasattr(response_obj, 'text') else 'N/A'
            logger.error(f"Invalid JSON from LLM '{llm_config.get('model', llm_role_to_use)}': {e_json}. Response: {response_text_for_log}")
            return f"[Invalid JSON from LLM '{llm_config.get('model', llm_role_to_use)}']"
        except Exception as e_gen:
            logger.error(f"Failed to process response from LLM '{llm_config.get('model', llm_role_to_use)}': {e_gen}", exc_info=True)
            return f"[Failed to process response from LLM '{llm_config.get('model', llm_role_to_use)}': {e_gen}]"

    # ... (rest of the EthosCore methods: _run_memory_summarization, get_recent_dreams, etc.)
    # Ensure all methods from the "broken" file that are still relevant are included and corrected.

    async def get_last_proactive_action_time(self, user_id: str, action_type: str) -> Optional[datetime]:
        if not user_id or not action_type: return None
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        can_use_json_extract = True
        try:
            cursor.execute("SELECT json_extract('{\"key\":\"value\"}', '$.key')"); result = cursor.fetchone()
            if result is None or result[0] != 'value': can_use_json_extract = False
        except sqlite3.OperationalError as oe_test:
            if "no such function: json_extract" in str(oe_test).lower(): can_use_json_extract = False
            else: logger.error(f"Unexpected SQLite error checking json_extract: {oe_test}", exc_info=True); can_use_json_extract = False
        except Exception as e_test_other: logger.error(f"General error checking json_extract: {e_test_other}", exc_info=True); can_use_json_extract = False
        
        sql_query, params_list = "", [] # Renamed params to params_list to avoid conflict
        if can_use_json_extract:
            sql_query = "SELECT timestamp FROM memories WHERE type = 'proactive_action_record' AND json_extract(metadata, '$.user_id') = ? AND json_extract(metadata, '$.action_type') = ? ORDER BY timestamp DESC LIMIT 1"
            params_list = [user_id, action_type]
        else:
            logger.warning(f"json_extract not available for get_last_proactive_action_time (user: {user_id}, action: {action_type}).")
            sql_query = "SELECT timestamp, metadata FROM memories WHERE type = 'proactive_action_record' ORDER BY timestamp DESC LIMIT 100" 
        try:
            cursor.execute(sql_query, tuple(params_list)) # Use params_list
            if not can_use_json_extract:
                for row_data_raw in cursor.fetchall():
                    row_dict = dict(row_data_raw); metadata_str = row_dict.get('metadata')
                    if metadata_str and isinstance(metadata_str, str):
                        try:
                            metadata = json.loads(metadata_str)
                            if isinstance(metadata, dict) and metadata.get('user_id') == user_id and metadata.get('action_type') == action_type:
                                if ts_str := row_dict.get('timestamp'): return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        except (json.JSONDecodeError, ValueError, TypeError): continue
                return None
            else:
                if row := cursor.fetchone():
                    if ts_str := row['timestamp']: return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                return None
        except Exception as e: logger.error(f"Error retrieving last proactive action time for user '{user_id}', action '{action_type}': {e}", exc_info=True); return None


    async def get_todays_briefing_context_for_prompt(self, user_id: str) -> str:
        try:
            if not self.logos_core:
                logger.warning("EthosCore: LogosCore not available for get_todays_briefing_context_for_prompt.")
                return "Briefing service unavailable (LogosCore missing)."

            # Call LogosCore to get briefing data, which now includes classified_sentiment
            briefing_data = await self.logos_core.get_or_generate_daily_briefing(user_id_context=user_id)

            briefing_content_for_prompt = "No briefing available for Pathos today." # Default

            if briefing_data and briefing_data.get('success') and briefing_data.get('briefing_content'):
                content_str = str(briefing_data['briefing_content'])
                # Ensure content_str is not None before formatting; briefing_data.get already handles this.
                max_len = self.ethos_config.get('briefing_context_max_length_for_prompt', 1500)
                briefing_content_for_prompt = f"Today's Briefing Highlights (Pathos's context, shared with user '{user_id}'):\n{content_str[:max_len] + '...' if len(content_str) > max_len else content_str}"

                # Trigger Hexus update based on classified sentiment from briefing_data
                classified_sentiment = briefing_data.get('classified_sentiment') # This is new
                if classified_sentiment:
                    event_name: Optional[str] = None
                    if classified_sentiment == 'positive':
                        event_name = "BRIEFING_OVERALL_POSITIVE"
                    elif classified_sentiment == 'negative':
                        event_name = "BRIEFING_OVERALL_NEGATIVE"
                    elif classified_sentiment == 'neutral': # Ensure 'neutral' is handled
                        event_name = "BRIEFING_OVERALL_NEUTRAL"

                    if event_name:
                        logger.debug(f"EthosCore: Triggering Hexus event '{event_name}' based on briefing sentiment '{classified_sentiment}'.")
                        # Since get_todays_briefing_context_for_prompt is async, direct await is fine.
                        # If this method were sync, asyncio.create_task would be appropriate.
                        await self.process_event_for_hexus_update(
                            event_type=event_name, # Ensure param name matches definition
                            payload={"briefing_source": briefing_data.get("source", "unknown"), "user_id": user_id}
                        )
                    else:
                        # This case should ideally not be hit if LogosCore always returns a valid default.
                        logger.warning(f"EthosCore: Unknown or unhandled classified sentiment for briefing: '{classified_sentiment}'")
                else:
                    logger.debug("EthosCore: No classified sentiment found in briefing_data to trigger Hexus update.")
            else:
                 # Log if briefing_data indicates failure or no content
                 logger.info(f"EthosCore: Briefing data not successful or content missing. Success: {briefing_data.get('success')}, Content Present: {bool(briefing_data.get('briefing_content'))}")


            return briefing_content_for_prompt

        except Exception as e:
            logger.error(f"Error getting briefing context for prompt: {e}", exc_info=True)
            return "Briefing information temporarily unavailable (error)"
    
    async def get_pathos_aspirations_context_for_prompt(self) -> str:
        try:
            max_items = self.ethos_config.get('aspiration_context_max_items_for_prompt', 5)
            aspirations = await self.memory_storage.get_entries_by_type_and_user("aspiration", PATHOS_USER_ID, max_items)
            if not aspirations: return "Pathos has no current aspirations defined."
            lines = ["Pathos's Current Aspirations:"]
            for entry in aspirations:
                if content_str := entry.get('content'):
                    try:
                        content_data = json.loads(content_str)
                        title = content_data.get('title', str(content_data)) if isinstance(content_data, dict) else str(content_data)
                        status = content_data.get('status', 'unknown')
                        lines.append(f"- {title} (Status: {status})")
                    except json.JSONDecodeError: lines.append(f"- {content_str[:100]}...")
            return "\n".join(lines)
        except Exception as e: logger.error(f"Error getting Pathos aspirations context: {e}", exc_info=True); return "Aspirations information for Pathos is temporarily unavailable (error)"    
    
    async def get_pathos_schedule_context_for_prompt(self) -> str:
        try:
            if not self.chronos_engine:
                logger.warning("EthosCore.get_pathos_schedule_context_for_prompt: ChronosEngine not available.")
                return "Schedule information for Pathos is temporarily unavailable (system component missing)."
            schedule: List['ActivitySlot'] = await self.chronos_engine.get_todays_schedule_for_user() 
            if not schedule: return "Pathos has no scheduled activities for today."
            lines = ["Pathos's Schedule for Today:"]
            max_items = self.ethos_config.get('schedule_context_max_items_for_prompt', 5)
            desc_snippet_len = self.ethos_config.get('schedule_context_desc_snippet_len', 50)
            for activity in schedule[:max_items]:
                time_str = f"{activity.start_time.strftime('%H:%M')}-{activity.end_time.strftime('%H:%M')}"
                line = f"- {time_str}: {activity.activity_title}"
                if activity.activity_details and activity.activity_details.description:
                    desc_snippet = activity.activity_details.description[:desc_snippet_len]
                    line += f" (Focus: {desc_snippet}{'...' if len(activity.activity_details.description) > desc_snippet_len else ''})"
                lines.append(line)
            if len(schedule) > max_items: lines.append(f"- ...and {len(schedule) - max_items} more activities.")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error getting Pathos schedule context for prompt: {e}", exc_info=True)
            return "Schedule information for Pathos is temporarily unavailable (error)"    
    
    async def get_user_profile_summary(self, user_id: str) -> str:
        if not user_id or user_id in self.system_user_ids:
            return "No specific profile information available for this user yet."
        facts = await self.get_all_user_facts(user_id)
        if not facts: return "No specific profile information available for this user yet."
        parts = []
        for fact_entry in facts[:5]: 
            try:
                content_str = fact_entry.get('content')
                if content_str and isinstance(content_str, str):
                    content_data = json.loads(content_str)
                    attribute_name = content_data.get('attribute', 'unknown_attribute')
                    attribute_value = content_data.get('value', 'unknown_value')
                    display_key = attribute_name.replace('_', ' ').title()
                    display_value = str(attribute_value)
                    if len(display_value) > 70: display_value = display_value[:67] + "..."
                    if display_key.lower() == 'name': parts.insert(0, f"Name: {display_value}")
                    elif display_key.lower() == 'preferred location': parts.append(f"Location: {display_value}")
                    else: parts.append(f"{display_key}: {display_value}")
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"Could not parse user fact for profile summary (user: {user_id}, fact_id: {fact_entry.get('id')}): {e}")
                continue
        if not parts: return "No specific profile information available for this user yet."
        return f"User profile for '{user_id}': {'; '.join(parts)}."    
    
    async def get_all_user_facts(self, user_id: str) -> List[MemoryEntry]:
        if not user_id or user_id in self.system_user_ids:
            logger.debug(f"get_all_user_facts called for system/invalid user '{user_id}', returning empty list.")
            return []
        
        logger.debug(f"EthosCore: Fetching all user facts for user_id: {user_id}")
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        can_use_json_extract = True
        try:
            cursor.execute("SELECT json_extract('{\"key\":\"value\"}', '$.key')"); result = cursor.fetchone()
            if result is None or result[0] != 'value': can_use_json_extract = False
        except sqlite3.OperationalError as oe_test:
            if "no such function: json_extract" in str(oe_test).lower(): can_use_json_extract = False
            else: logger.error(f"Unexpected SQLite error checking json_extract: {oe_test}", exc_info=True); can_use_json_extract = False
        except Exception as e_test_other: logger.error(f"General error checking json_extract: {e_test_other}", exc_info=True); can_use_json_extract = False

        facts_entries: List[MemoryEntry] = []
        sql_query_str, params_list = "", [] # Renamed params to params_list
        if can_use_json_extract:
            sql_query_str = "SELECT * FROM memories WHERE type = 'user_fact' AND json_extract(metadata, '$.user_id') = ? AND json_extract(metadata, '$.fact_attribute_key') IS NOT NULL AND (is_archived = 0 OR is_archived IS NULL) ORDER BY timestamp DESC"
            params_list = [user_id]
        else:
            logger.warning(f"json_extract not available for get_all_user_facts (user: {user_id}). This will be less efficient.")
            sql_query_str = "SELECT * FROM memories WHERE type = 'user_fact' AND (is_archived = 0 OR is_archived IS NULL) ORDER BY timestamp DESC"
            # params_list remains empty
        try:
            cursor.execute(sql_query_str, tuple(params_list)); rows_raw = cursor.fetchall() # Use params_list
            latest_facts_by_attribute: Dict[str, MemoryEntry] = {}
            for row_data_raw in rows_raw:
                entry = self.memory_storage._row_to_entry(dict(row_data_raw))
                metadata = entry.get('metadata', {}); entry_user_id = metadata.get('user_id'); attribute_key = metadata.get('fact_attribute_key')
                if not can_use_json_extract:
                    if entry_user_id != user_id or not attribute_key: continue
                if attribute_key and attribute_key not in latest_facts_by_attribute:
                    latest_facts_by_attribute[attribute_key] = entry
            facts_entries = list(latest_facts_by_attribute.values())
            facts_entries.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            logger.info(f"Retrieved {len(facts_entries)} unique user facts for user '{user_id}'.")
            return facts_entries
        except Exception as e: logger.error(f"Error retrieving all user facts for user '{user_id}': {e}", exc_info=True); return []
    
    async def get_current_activity_description(self) -> str:
        try:
            if not self.chronos_engine:
                logger.warning("EthosCore.get_current_activity_description: ChronosEngine not available.")
                return "Activity information temporarily unavailable (system component missing)."
            pathos_local_now = await self.get_local_datetime_for_user(PATHOS_USER_ID) 
            current_activity: Optional['ActivitySlot'] = await self.chronos_engine.get_current_activity(pathos_local_now)
            if current_activity:
                desc = f"Currently: {current_activity.activity_title}"
                if current_activity.activity_details and current_activity.activity_details.description:
                    desc += f" - {current_activity.activity_details.description}"
                if current_activity.activity_details and current_activity.activity_details.location_context:
                    desc += f" (Location: {current_activity.activity_details.location_context})"
                return desc
            return "No scheduled activity for Pathos at the moment."
        except Exception as e:
            logger.error(f"Error getting current activity description: {e}", exc_info=True)
            return "Activity information temporarily unavailable (error)"
    
    async def get_queued_discussion_points(self, user_id: str, limit: int = 1) -> List[MemoryEntry]:
        if not user_id: return []
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        can_use_json_extract = True
        try:
            cursor.execute("SELECT json_extract('{\"key\":\"value\"}', '$.key')"); result = cursor.fetchone()
            if result is None or result[0] != 'value': can_use_json_extract = False
        except Exception: can_use_json_extract = False
        
        queued_points: List[MemoryEntry] = []; fetch_limit = limit * 2 if limit > 0 else 10
        sql_query_str, params_list = "", [] # Renamed params to params_list
        if can_use_json_extract:
            sql_query_str = "SELECT * FROM memories WHERE type = 'queued_discussion_point' AND (json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') IS NULL) AND (json_extract(metadata, '$.status') IS NULL OR json_extract(metadata, '$.status') = 'pending') ORDER BY salience DESC, timestamp ASC LIMIT ?"
            params_list = [user_id, "system_oneiros", fetch_limit] 
        else:
            logger.warning("json_extract not available for get_queued_discussion_points. Querying all and filtering in Python.")
            sql_query_str = "SELECT * FROM memories WHERE type = 'queued_discussion_point' ORDER BY timestamp DESC LIMIT ?"
            params_list = [fetch_limit * 5] 
        
        cursor.execute(sql_query_str, tuple(params_list)); rows_raw = cursor.fetchall()
        for row_data_raw in rows_raw:
            try:
                entry = self.memory_storage._row_to_entry(dict(row_data_raw)); metadata = entry.get('metadata', {})
                entry_user_id = metadata.get('user_id'); status = metadata.get('status', 'pending')
                if not can_use_json_extract:
                    if status != 'pending': continue
                    if not (entry_user_id == user_id or entry_user_id == "system_oneiros" or entry_user_id is None or entry_user_id == PATHOS_USER_ID): continue
                queued_points.append(entry)
            except Exception as e_entry: logger.error(f"Error processing queued point entry: {e_entry}", exc_info=True)
        
        queued_points.sort(key=lambda x: (-(float(x.get('salience', 0.0)) if x.get('salience') is not None else 0.0), x.get('timestamp', '') or ''), reverse=False)
        final_limit = queued_points[:limit]
        logger.info(f"Retrieved {len(final_limit)} queued discussion points for user_id: {user_id} (Limit: {limit}, Fetched before sort/filter: {len(rows_raw)}, After initial filter: {len(queued_points)})")
        return final_limit
    
    async def clear_memory_for_user(self, user_id: str) -> bool:
        if not user_id or not user_id.strip(): return False
        try: return self.memory_storage.delete_entries_by_user_id(user_id)
        except Exception as e: logger.error(f"Error clearing memory for user '{user_id}': {e}", exc_info=True); return False

    async def get_recent_learnings(self, learning_types: List[str], user_id_context: Optional[str], limit: int) -> List[MemoryEntry]:
        if not learning_types or limit <= 0: return []
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()

        placeholders = ','.join('?' * len(learning_types))
        # Modified SQL base to include is_archived filter
        sql = f"SELECT * FROM memories WHERE type IN ({placeholders}) AND (is_archived = 0 OR is_archived IS NULL)"

        params: List[Any] = list(learning_types)
        can_use_json = True
        try:
            cursor.execute("SELECT json_extract('{\"k\":\"v\"}', '$.k')")
        except sqlite3.OperationalError:
            can_use_json = False
            logger.warning("json_extract not available for get_recent_learnings. User filtering will be done in Python.")
        
        # Append user_id filtering logic
        if can_use_json:
            if user_id_context and user_id_context not in self.system_user_ids:
                sql += " AND (json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') = ?)"
                params.extend([user_id_context, PATHOS_USER_ID])
            elif user_id_context in self.system_user_ids or not user_id_context: # System or general context
                sql += " AND (json_extract(metadata, '$.user_id') = ? OR json_extract(metadata, '$.user_id') IS NULL)" # Pathos's own or truly global (NULL user_id)
                params.append(PATHOS_USER_ID)

        fetch_limit_for_sql = limit
        # Determine if Python-side filtering for user_id will be needed
        needs_python_user_filter = not can_use_json and user_id_context is not None

        if needs_python_user_filter:
            fetch_limit_for_sql = limit * 5 # Fetch more if user_id filtering will happen in Python
            logger.debug(f"Adjusted fetch limit for get_recent_learnings to {fetch_limit_for_sql} due to Python-based user_id filtering for user '{user_id_context}'.")

        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(fetch_limit_for_sql)
        
        try:
            logger.debug(f"Executing get_recent_learnings query: {sql} with params: {params}")
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
            learnings: List[MemoryEntry] = []
            for row_data in rows:
                entry = self.memory_storage._row_to_entry(dict(row_data))
                entry_uid = entry.get('metadata', {}).get('user_id')

                if needs_python_user_filter:
                    # Apply Python-side user_id filtering if json_extract was not available for it
                    if user_id_context and user_id_context not in self.system_user_ids: # Specific user context
                        if not (entry_uid == user_id_context or entry_uid == PATHOS_USER_ID):
                            continue
                    # This 'else' handles 'user_id_context in self.system_user_ids or not user_id_context'
                    # which means we want Pathos's own (PATHOS_USER_ID) or truly global (user_id is None)
                    elif not (entry_uid == PATHOS_USER_ID or entry_uid is None):
                            continue

                learnings.append(entry)

            # If Python user filtering happened, the list might be longer than the original limit before this step.
            # The SQL already sorted by timestamp, so direct slicing is fine.
            return learnings[:limit]
        except Exception as e:
            logger.error(f"Error retrieving learnings (types: {learning_types}, user: {user_id_context}): {e}", exc_info=True)
            return []

    async def get_recent_knowledge_verifications(self, limit: int = 20) -> List[MemoryEntry]:
        conn = self.memory_storage._get_connection(); cursor = conn.cursor()
        # Added (is_archived = 0 OR is_archived IS NULL)
        sql = "SELECT * FROM memories WHERE type = 'world_knowledge' AND json_extract(metadata, '$.last_verified_timestamp') IS NOT NULL AND (is_archived = 0 OR is_archived IS NULL) ORDER BY json_extract(metadata, '$.last_verified_timestamp') DESC LIMIT ?"
        oe_msg = ""
        try: cursor.execute(sql, (limit,))
        except sqlite3.OperationalError as oe:
            oe_msg = str(oe).lower()
            if "no such function: json_extract" in oe_msg:
                # Added (is_archived = 0 OR is_archived IS NULL)
                sql_fb = "SELECT * FROM memories WHERE type = 'world_knowledge' AND (is_archived = 0 OR is_archived IS NULL) ORDER BY timestamp DESC LIMIT ?" # Less ideal sort
                cursor.execute(sql_fb, (limit * 5,)) # Fetch more for Python filtering
            else: raise
        
        rows = cursor.fetchall(); verifications: List[MemoryEntry] = []
        for row_data in rows:
            entry = self.memory_storage._row_to_entry(dict(row_data))
            if "no such function: json_extract" in oe_msg and entry.get('metadata', {}).get('last_verified_timestamp') is None:
                continue # Python filter if json_extract failed
            verifications.append(entry)
        
        if "no such function: json_extract" in oe_msg: # Re-sort if we had to Python filter
            verifications.sort(key=lambda x: x.get('metadata', {}).get('last_verified_timestamp', '0000-00-00T00:00:00Z'), reverse=True)
        
        return verifications[:limit]

    async def get_user_profile_summary(self, user_id: str) -> str:
        if not user_id or user_id in self.system_user_ids:
            return "No specific profile information available for this user yet."
        
        facts = await self.get_all_user_facts(user_id)
        if not facts:
            return "No specific profile information available for this user yet."
        
        parts = []
        for fact_entry in facts[:5]: # Limit for brevity
            try:
                content_str = fact_entry.get('content')
                if content_str and isinstance(content_str, str):
                    content_data = json.loads(content_str)
                    attribute_name = content_data.get('attribute', 'unknown_attribute')
                    attribute_value = content_data.get('value', 'unknown_value')
                    display_key = attribute_name.replace('_', ' ').title()
                    display_value = str(attribute_value)
                    if len(display_value) > 70: display_value = display_value[:67] + "..."
                    if display_key.lower() == 'name': parts.insert(0, f"Name: {display_value}")
                    elif display_key.lower() == 'preferred location': parts.append(f"Location: {display_value}")
                    else: parts.append(f"{display_key}: {display_value}")
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning(f"Could not parse user fact for profile summary (user: {user_id}, fact_id: {fact_entry.get('id')}): {e}")
                continue
        
        if not parts: return "No specific profile information available for this user yet."
        return f"User profile for '{user_id}': {'; '.join(parts)}."

    def get_persona_directives(self) -> List[str]: # ADDED METHOD
        """Returns the loaded persona directives for Pathos."""
        return self.persona_directives

    async def run_reflection_cycle(self): # ADDED METHOD (Placeholder)
        """
        Placeholder for the Ethos Reflection Cycle.
        This cycle is intended for deeper analysis of recent interactions,
        memory consolidation, insight generation, and self-correction.
        """
        if not any([self.config.ENABLE_LEARNING_FROM_FEEDBACK, self.config.ENABLE_CURIOUSITY, self.ethos_config.get('enable_memory_summarization', False), self.config.ENABLE_PROACTIVE_BEHAVIOR]):
            logger.debug("EthosReflection cycle skipped as all related features are disabled.")
            return

        now = datetime.now(timezone.utc)
        logger.info(f"--- Ethos: Starting Reflection Cycle (Placeholder) ---")
        # Actual reflection logic would go here.
        # For example:
        # 1. Retrieve recent interactions and feedback.
        # 2. Analyze for patterns, successes, failures.
        # 3. Generate insights or new knowledge (e.g., world_knowledge, learned_correction).
        # 4. Update Hexus scores based on reflection.
        # 5. Queue discussion points for Pathos or user.
        await asyncio.sleep(10) # Simulate work

        self.last_reflection_time = now
        self._save_task_last_run_time("EthosReflection", now)
        logger.info(f"--- Ethos: Reflection Cycle Finished (Placeholder) ---")

    async def run_reflection_cycle(self):
        """
        Performs a reflection cycle:
        1. Fetches recent relevant memories.
        2. Filters and selects the most salient/significant ones.
        3. Formats them for an LLM.
        4. Calls an LLM to generate insights based on these memories.
        5. Stores these insights as new memories.
        6. Updates Hexus scores based on the reflection.
        """
        now = datetime.now(timezone.utc)
        logger.info(f"--- Ethos: Starting Reflection Cycle at {now.isoformat()} ---")

        # 1. Retrieve Configuration
        reflection_llm_role = self.ethos_config.get('reflection_llm_role', "LOGOS_TECHNE")
        query_limit = self.ethos_config.get('reflection_memory_query_limit', 50)
        max_memories_for_llm = self.ethos_config.get('reflection_max_memories_for_llm', 15)
        min_salience_for_consideration = self.ethos_config.get('reflection_min_salience_for_consideration', 0.3)
        significant_event_threshold = self.ethos_config.get('reflection_significant_event_salience_threshold', 0.7)
        lookback_days = self.ethos_config.get('reflection_lookback_days', 3)

        # 2. Fetch Memories
        memories_for_reflection = await self._get_memories_for_reflection(lookback_days, query_limit)
        if not memories_for_reflection:
            logger.info("Reflection Cycle: No memories found for reflection period. Cycle ending.")
            self.last_reflection_time = now # Still update time to avoid immediate re-run
            self._save_task_last_run_time("EthosReflection", now)
            return

        # 3. Filter and Select Salient Memories
        # Filter by min_salience
        considered_memories = [
            mem for mem in memories_for_reflection
            if mem.get('salience', 0.0) >= min_salience_for_consideration
        ]

        if not considered_memories:
            logger.info(f"Reflection Cycle: No memories met minimum salience ({min_salience_for_consideration}). Cycle ending.")
            self.last_reflection_time = now
            self._save_task_last_run_time("EthosReflection", now)
            return

        # Prioritize: simple scoring - significant events and feedback get higher priority
        def get_priority_score(memory: MemoryEntry) -> float:
            score = memory.get('salience', 0.0)
            if memory.get('type') == 'feedback':
                score += 0.5 # Boost feedback
            if memory.get('salience', 0.0) >= significant_event_threshold:
                score += 0.3 # Boost very salient events
            # Negative feedback could also be prioritized if needed by adding more conditions
            return score

        considered_memories.sort(key=get_priority_score, reverse=True)
        selected_memories = considered_memories[:max_memories_for_llm]
        source_memory_ids = [mem.get('id') for mem in selected_memories if mem.get('id')]

        if not selected_memories:
            logger.info("Reflection Cycle: No memories selected for LLM after prioritization. Cycle ending.")
            self.last_reflection_time = now
            self._save_task_last_run_time("EthosReflection", now)
            return

        logger.info(f"Reflection Cycle: Selected {len(selected_memories)} memories for LLM prompt.")

        # 4. Format Memories for LLM Prompt
        formatted_memory_strings = []
        for mem in selected_memories:
            ts_str = mem.get('timestamp', "Unknown time")
            try: # Format timestamp nicely
                ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                formatted_ts = ts_dt.strftime("%Y-%m-%d %H:%M UTC")
            except ValueError:
                formatted_ts = ts_str

            content_snippet = (mem.get('content', '') or "")[:150] + "..." if len(mem.get('content', '') or "") > 150 else mem.get('content', '')
            mood_info = ""
            if mem_meta := mem.get('metadata'):
                if mood_at_res := mem_meta.get('mood_at_response'): # from chat_interaction
                    mood_name = mood_at_res.get('name', 'unknown')
                    mood_info = f" (Mood: {mood_name}, V:{mood_at_res.get('valence',0):.1f}, A:{mood_at_res.get('arousal',0):.1f})"
                elif mem_meta.get('mood_valence_at_time') is not None: # from firmament_activity_log
                    mood_info = f" (Mood: {mem_meta.get('mood_name_at_time', 'unknown')}, V:{mem_meta.get('mood_valence_at_time',0):.1f}, A:{mem_meta.get('mood_arousal_at_time',0):.1f})"

            formatted_memory_strings.append(
                f"- Timestamp: {formatted_ts}, Type: {mem.get('type')}, Salience: {mem.get('salience', 0.0):.2f}{mood_info}\n  Content: {content_snippet}"
            )
        memories_block_for_prompt = "\n".join(formatted_memory_strings)

        # 5. Construct LLM Prompt
        system_prompt = (
            "You are a reflective journaling assistant for an AI named Pathos. "
            "Review the following list of recent experiences, thoughts, and feedback. "
            "Identify 2-3 key insights, self-observations, or lessons learned from these memories. "
            "Focus on patterns, significant events, or areas for growth or understanding. "
            "Insights should be concise and actionable or thought-provoking for Pathos. "
            "Your output MUST be a JSON object containing a single key \"insights\" which is a list of strings. "
            "Example: {\"insights\": [\"Insight text 1.\", \"Insight text 2.\"]}"
        )
        user_prompt = (
            "Here is a selection of Pathos's recent memories for reflection:\n\n"
            f"{memories_block_for_prompt}\n\n"
            "Please generate 2-3 concise insights based on these memories, in the specified JSON format."
        )
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

        # 6. Call LLM for Reflection
        llm_response_str = await self._call_llm_for_internal_task(messages, reflection_llm_role)

        if not llm_response_str or not llm_response_str.strip():
            logger.warning("Reflection Cycle: LLM call returned no content. Cycle ending.")
            self.last_reflection_time = now
            self._save_task_last_run_time("EthosReflection", now)
            return

        # 7. Process LLM Response and Store Insights
        try:
            # Attempt to find JSON block within potentially messy LLM output
            json_match = re.search(r'\{[\s\S]*\}', llm_response_str)
            if not json_match:
                logger.error(f"Reflection Cycle: No JSON object found in LLM response. Raw response: {llm_response_str}")
                self.last_reflection_time = now
                self._save_task_last_run_time("EthosReflection", now)
                return

            parsed_response = json.loads(json_match.group(0))

            if isinstance(parsed_response, dict) and "insights" in parsed_response and isinstance(parsed_response["insights"], list):
                insights = parsed_response["insights"]
                if not insights:
                    logger.info("Reflection Cycle: LLM generated an empty list of insights.")
                else:
                    logger.info(f"Reflection Cycle: LLM generated {len(insights)} insights.")
                    current_hexus_snapshot = self.get_hexus_scores() # Get current scores to associate with insight
                    for insight_text in insights:
                        if not isinstance(insight_text, str) or not insight_text.strip():
                            logger.warning(f"Reflection Cycle: Skipping empty or invalid insight: {insight_text}")
                            continue

                        new_insight_entry_data = {
                            "type": "reflection_insight",
                            "content": insight_text.strip(),
                            "metadata": {
                                "source_reflection_cycle_timestamp": now.isoformat(),
                                "source_memory_ids": source_memory_ids,
                                "hexus_at_reflection": current_hexus_snapshot,
                                "user_id": PATHOS_USER_ID # Insight belongs to Pathos
                            },
                            "salience": 0.85, # Insights are highly salient
                            "user_id": PATHOS_USER_ID
                        }
                        await self.add_memory_entry(new_insight_entry_data, user_id_context=PATHOS_USER_ID)
                        logger.info(f"Reflection Cycle: Stored insight - '{insight_text[:100]}...'")

                    # 8. Hexus Score Updates (Simplified First Pass)
                    await self.process_event_for_hexus_update("REFLECTION_CYCLE_COMPLETED_INSIGHTS", payload={"num_insights": len(insights)})

            else:
                logger.error(f"Reflection Cycle: LLM response JSON does not match expected structure ('insights' list). Raw response: {llm_response_str}")

        except json.JSONDecodeError as e:
            logger.error(f"Reflection Cycle: Failed to parse LLM response as JSON: {e}. Raw response: {llm_response_str}")
        except Exception as e_proc:
            logger.error(f"Reflection Cycle: Error processing LLM response or storing insights: {e_proc}", exc_info=True)

        # 9. Update Timestamps
        self.last_reflection_time = now
        self._save_task_last_run_time("EthosReflection", now)
        logger.info(f"--- Ethos: Reflection Cycle Finished at {now.isoformat()} ---")
        # Call aspiration generation after successful reflection if insights were generated
        if insights_generated: # Assuming 'insights_generated' boolean is set if insights were made # TODO: Ensure insights_generated is correctly set
            await self._generate_new_aspirations()

    async def run_knowledge_upkeep(self):
        """
        Periodically reviews 'world_knowledge' facts, verifies them (simplified for now),
        and updates their 'last_verified_timestamp'.
        """
        if not self.config.ENABLE_KNOWLEDGE_UPKEEP:
            logger.debug("Knowledge upkeep cycle skipped as feature is disabled by Config.ENABLE_KNOWLEDGE_UPKEEP.")
            return

        now = datetime.now(timezone.utc)
        logger.info(f"--- Ethos: Starting Knowledge Upkeep Cycle at {now.isoformat()} ---")

        # 1. Retrieve Configuration
        # llm_role = self.ethos_config.get('knowledge_upkeep_llm_role', "LOGOS_TECHNE") # For future LLM-based verification
        max_facts_to_review = self.ethos_config.get('knowledge_upkeep_max_facts_to_review', 5)
        min_days_before_review = self.ethos_config.get('knowledge_upkeep_min_days_before_review', 30)

        if not self.memory_storage:
            logger.error("EthosCore: MemoryStorage not available. Cannot run knowledge upkeep.")
            self.last_knowledge_upkeep_time = now # Update time to prevent immediate re-run on error
            self._save_task_last_run_time("KnowledgeUpkeep", now)
            return

        # 2. Get Facts for Review
        facts_for_review = await self.memory_storage.get_knowledge_facts_for_review(
            min_days_since_last_review=min_days_before_review,
            limit=max_facts_to_review
        )

        if not facts_for_review:
            logger.info("Knowledge Upkeep: No facts found requiring review at this time.")
            self.last_knowledge_upkeep_time = now
            self._save_task_last_run_time("KnowledgeUpkeep", now)
            return

        logger.info(f"Knowledge Upkeep: Found {len(facts_for_review)} facts to review.")
        updated_count = 0

        # 3. Process Each Fact
        for fact_entry in facts_for_review:
            fact_id = fact_entry.get('id')
            if not fact_id:
                logger.warning("Knowledge Upkeep: Found fact entry with no ID. Skipping.")
                continue

            logger.info(f"Knowledge Upkeep: Reviewing fact ID {fact_id} - '{str(fact_entry.get('content',''))[:50]}...'")

            # ** SIMPLIFIED VERIFICATION **
            # In a basic pass, we skip actual LLM/web verification.
            # We just update the timestamp and add a note.

            current_metadata = fact_entry.get('metadata', {}).copy() # Ensure it's a mutable copy
            current_metadata['last_verified_timestamp'] = now.isoformat()
            current_metadata['verification_notes'] = "Reviewed by automated knowledge upkeep cycle (basic pass)."
            # Optional: Could add a counter for how many times it's been reviewed.
            # current_metadata['verification_cycle_count'] = current_metadata.get('verification_cycle_count', 0) + 1

            update_payload = {'metadata': current_metadata}

            if self.memory_storage.update_entry(fact_id, update_payload):
                logger.info(f"Knowledge Upkeep: Successfully updated metadata for fact ID {fact_id}.")
                updated_count += 1
            else:
                logger.warning(f"Knowledge Upkeep: Failed to update metadata for fact ID {fact_id}.")

        # 4. Update Timestamps and Log Completion
        self.last_knowledge_upkeep_time = now
        self._save_task_last_run_time("KnowledgeUpkeep", now)
        logger.info(f"--- Ethos: Knowledge Upkeep Cycle Finished. Reviewed and updated {updated_count}/{len(facts_for_review)} facts. ---")


    async def _generate_new_aspirations(self) -> None:
        """
        Generates new long-term aspirations for Pathos based on recent insights and experiences.
        Called at the end of a reflection cycle.
        """
        logger.info("--- Ethos: Starting Aspiration Generation ---")
        num_seed_memories = self.ethos_config.get('aspiration_num_seed_memories', 15)
        min_salience_seed = self.ethos_config.get('aspiration_min_salience_seed', 0.5)
        llm_role = self.ethos_config.get('aspiration_generation_llm_role', "LOGOS_TECHNE")
        # Use a lookback similar to reflection, or a dedicated one if configured
        lookback_days_for_seeds = self.ethos_config.get('reflection_lookback_days', 7)

        seed_memory_types = ['reflection_insight', 'feedback', 'chat_interaction',
                             'firmament_activity_log', 'learned_correction', 'world_knowledge']


        # Changed to get_memories_for_summary, removed sort_by_salience_then_recency
        # The default sort of get_memories_for_summary (salience then recency) matches the intent.
        candidate_memories = await self.memory_storage.get_memories_for_summary(
            user_id=PATHOS_USER_ID,
            start_time_utc=datetime.now(timezone.utc) - timedelta(days=lookback_days_for_seeds),
            end_time_utc=datetime.now(timezone.utc),
            types=seed_memory_types,
            limit=num_seed_memories * 3
            # include_archived defaults to False

        )

        seed_memories = [mem for mem in candidate_memories if mem.get('salience', 0.0) >= min_salience_seed][:num_seed_memories]

        if len(seed_memories) < 3:
            logger.info(f"Not enough salient seed memories ({len(seed_memories)}) for aspirations. Min required: 3, Min Salience: {min_salience_seed}.")
            return

        formatted_seeds = []
        for mem in seed_memories:
            ts_str = mem.get('timestamp', "Unknown time")
            try: ts_dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00")); formatted_ts = ts_dt.strftime("%Y-%m-%d")
            except ValueError: formatted_ts = ts_str
            content_snippet = (mem.get('content', '') or "")[:100] + "..." if len(mem.get('content', '') or "") > 100 else mem.get('content', '')
            formatted_seeds.append(f"- [{formatted_ts}, Type: {mem.get('type')}, Sal: {mem.get('salience',0.0):.2f}]: {content_snippet}")

        seeds_block = "\n".join(formatted_seeds)
        system_prompt = (
            "You are an AI assistant helping Pathos formulate 1-2 new long-term aspirational goals. "
            "Based on the provided recent experiences and insights, identify potential areas for growth, learning, or significant long-term projects. "
            "Aspirations should be phrased from Pathos's perspective (e.g., 'I want to learn X', 'I aim to Y'). "
            "They should be high-level and achievable over weeks or months. "
            "Output MUST be a JSON object like: {\"aspirations\": [\"Aspiration 1 text\", \"Aspiration 2 text\"]}"
        )
        user_prompt = f"Pathos's recent salient experiences and insights:\n{seeds_block}\n\nNew aspirations (JSON format, 1-2 items):"
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

        llm_response = await self._call_llm_for_internal_task(messages, llm_role)
        if not llm_response: logger.warning("Aspiration generation LLM call returned no content."); return

        try:
            json_match = re.search(r'\{[\s\S]*\}', llm_response)
            if not json_match: logger.error(f"No JSON in aspiration LLM response: {llm_response}"); return
            parsed_response = json.loads(json_match.group(0))

            if isinstance(parsed_response, dict) and "aspirations" in parsed_response and isinstance(parsed_response["aspirations"], list):
                new_aspirations_text = parsed_response["aspirations"]
                if new_aspirations_text:
                    logger.info(f"Generated {len(new_aspirations_text)} new aspirations.")
                    for asp_text in new_aspirations_text:
                        if not isinstance(asp_text, str) or not asp_text.strip(): continue

                        asp_content_dict = {"title": asp_text.strip(), "description": "A newly generated long-term aspiration for Pathos."}
                        asp_metadata = {
                            "status": "active",
                            "generated_at": datetime.now(timezone.utc).isoformat(),
                            "source": "aspiration_generation_cycle",
                            "user_id": PATHOS_USER_ID,
                            "seed_memory_ids": [m.get('id') for m in seed_memories if m.get('id')]
                        }
                        await self.add_memory_entry(
                            {"type": "aspiration", "content": json.dumps(asp_content_dict),
                             "metadata": asp_metadata, "salience": 0.9},
                            user_id_context=PATHOS_USER_ID
                        )
                        logger.info(f"Stored new aspiration: '{asp_text[:100]}...'")
                else:
                    logger.info("Aspiration generation: LLM returned an empty list of aspirations.")
            else:
                logger.error(f"Aspiration LLM response JSON has incorrect structure: {llm_response}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse aspiration LLM JSON: {e}. Raw response: {llm_response}")
        except Exception as e:
            logger.error(f"Error processing new aspirations: {e}", exc_info=True)
        logger.info("--- Ethos: Aspiration Generation Finished ---")

    async def run_long_term_planning(self) -> None:
        """
        Reviews active aspirations and breaks them down into actionable high-level steps.
        """
        now = datetime.now(timezone.utc)
        logger.info(f"--- Ethos: Starting Long-Term Planning Cycle at {now.isoformat()} ---")

        llm_role = self.ethos_config.get('long_term_planning_llm_role', "LOGOS_TECHNE")
        max_aspirations_to_consider = self.ethos_config.get('long_term_planning_max_aspirations_to_consider', 2)

        if not self.memory_storage:
            logger.error("EthosCore: MemoryStorage not available. Cannot run long-term planning.")
            self.last_long_term_planning_time = now # Update time to prevent immediate re-run on error
            self._save_task_last_run_time("PathosLongTermPlanning", now)
            return

        active_aspirations = await self.memory_storage.get_entries_by_type_and_user(
            entry_type="aspiration",
            user_id=PATHOS_USER_ID,
            limit=max_aspirations_to_consider * 2 # Fetch more to filter by status
        )

        # Filter for only 'active' status aspirations and limit
        active_aspirations = [
            asp for asp in active_aspirations
            if asp.get("metadata", {}).get("status") == "active"
        ][:max_aspirations_to_consider]

        if not active_aspirations:
            logger.info("Long-Term Planning: No active aspirations found. Cycle ending.")
            self.last_long_term_planning_time = now
            self._save_task_last_run_time("PathosLongTermPlanning", now)
            return

        logger.info(f"Long-Term Planning: Considering {len(active_aspirations)} active aspirations.")

        for aspiration_entry in active_aspirations:
            aspiration_id = aspiration_entry.get('id')
            aspiration_content_str = aspiration_entry.get('content', '{}')
            try:
                aspiration_content_data = json.loads(aspiration_content_str)
                aspiration_title = aspiration_content_data.get('title', aspiration_content_str)
            except json.JSONDecodeError:
                aspiration_title = aspiration_content_str

            logger.info(f"Long-Term Planning: Generating plan steps for aspiration '{aspiration_title[:100]}...' (ID: {aspiration_id})")

            system_prompt = (
                "You are an AI assistant helping Pathos break down a long-term aspiration into 2-3 actionable, high-level steps or precursor goals. "
                "These steps should be distinct milestones. Output MUST be a JSON object: {\"plan_steps\": [\"Step 1 text\", \"Step 2 text\"]}"
            )
            user_prompt = f"Pathos's aspiration: \"{aspiration_title}\"\n\nHigh-level plan steps (JSON format):"
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

            llm_response = await self._call_llm_for_internal_task(messages, llm_role)

            if not llm_response:
                logger.warning(f"Long-Term Planning: LLM call for aspiration '{aspiration_title[:50]}' returned no content.")
                continue

            try:
                json_match = re.search(r'\{[\s\S]*\}', llm_response)
                if not json_match:
                    logger.error(f"No JSON in planning LLM response for aspiration '{aspiration_title[:50]}': {llm_response}"); continue
                parsed_response = json.loads(json_match.group(0))

                if isinstance(parsed_response, dict) and "plan_steps" in parsed_response and isinstance(parsed_response["plan_steps"], list):
                    plan_steps_text = parsed_response["plan_steps"]
                    if plan_steps_text:
                        logger.info(f"Generated {len(plan_steps_text)} plan steps for aspiration '{aspiration_title[:50]}'.")
                        for step_text in plan_steps_text:
                            if not isinstance(step_text, str) or not step_text.strip(): continue
                            step_metadata = {
                                "parent_aspiration_id": aspiration_id,
                                "parent_aspiration_text": aspiration_title,
                                "status": "pending",
                                "generated_at": now.isoformat(),
                                "user_id": PATHOS_USER_ID
                            }
                            await self.add_memory_entry(
                                {"type": "long_term_plan_step", "content": step_text.strip(),
                                 "metadata": step_metadata, "salience": 0.75, "user_id": PATHOS_USER_ID},
                                user_id_context=PATHOS_USER_ID
                            )
                            logger.info(f"Stored plan step for '{aspiration_title[:50]}': '{step_text[:100]}...'")
                    else:
                        logger.info(f"LLM generated an empty list of plan steps for aspiration '{aspiration_title[:50]}'.")
                else:
                    logger.error(f"Planning LLM response JSON bad structure for aspiration '{aspiration_title[:50]}': {llm_response}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse planning LLM JSON for '{aspiration_title[:50]}': {e}. Raw: {llm_response}")
            except Exception as e_step:
                 logger.error(f"Error processing plan steps for aspiration '{aspiration_title[:50]}': {e_step}", exc_info=True)

        self.last_long_term_planning_time = now
        self._save_task_last_run_time("PathosLongTermPlanning", now)
        logger.info(f"--- Ethos: Long-Term Planning Cycle Finished at {now.isoformat()} ---")

    async def run_managed_forgetting(self):
        """

        Manages memory decay and archival.
        1. Decays salience of unaccessed memories.
        2. Archives memories based on age and salience thresholds.
        Core memory types have different archival rules.

        if not self.config.ENABLE_MANAGED_FORGETTING:
            logger.debug("Managed forgetting cycle skipped as feature is disabled by Config.ENABLE_MANAGED_FORGETTING.")
            return

        now = datetime.now(timezone.utc)
        logger.info(f"--- Ethos: Starting Managed Forgetting Cycle at {now.isoformat()} ---")


        if not self.memory_storage:
            logger.error("EthosCore: MemoryStorage not available. Cannot run managed forgetting.")
            self.last_forgetting_time = now # Update time to prevent immediate re-run on error
            self._save_task_last_run_time("EthosForgetting", now)
            return

        # a. Salience Decay Step
        decay_rate = self.ethos_config.get('forgetting_salience_decay_rate_per_day', 0.01)
        min_floor = self.ethos_config.get('forgetting_min_salience_for_decay', 0.05)
        # days_since_accessed_threshold for decay is handled by memory_storage method's default (1 day)

        logger.info(f"Managed Forgetting: Starting salience decay. Rate: {decay_rate}/day, Floor: {min_floor}.")
        try:
            decayed_count = await asyncio.to_thread(
                self.memory_storage.decay_salience_for_unaccessed_memories,
                decay_rate,
                min_floor,
                self.forgetting_core_memory_types # Already parsed in __init__
            )
            logger.info(f"Managed Forgetting: Salience decay step completed. {decayed_count} memories had their salience decayed.")
        except Exception as e_decay:
            logger.error(f"Managed Forgetting: Error during salience decay step: {e_decay}", exc_info=True)
            # Decide if we should continue to archival or stop the cycle
            # For now, let's continue to archival, but log the error.

        # b. Archival Step
        logger.info("Managed Forgetting: Starting archival step.")

        salience_threshold_archive = self.ethos_config.get('forgetting_salience_threshold_archive', 0.1)
        days_to_archive_default = self.ethos_config.get('forgetting_days_to_archive_by_default', 90)
        extremely_low_salience_core = self.ethos_config.get('forgetting_extremely_low_salience_for_core', 0.01)

        archive_before_date = now - timedelta(days=days_to_archive_default)


        archived_count = 0
        processed_for_archival_count = 0
        batch_size = 200 # Configurable if needed
        offset = 0

        while True:
            candidate_memories_for_archive: List[MemoryEntry] = []
            try:
                candidate_memories_for_archive = await asyncio.to_thread(
                    self.memory_storage.get_all_unarchived_memories_for_forgetting_check,
                    batch_size,
                    offset
                )
            except Exception as e_fetch_archive:
                logger.error(f"Managed Forgetting: Error fetching memories for archival check (offset {offset}): {e_fetch_archive}", exc_info=True)
                break # Stop if fetching fails

            if not candidate_memories_for_archive:
                break

            processed_for_archival_count += len(candidate_memories_for_archive)
            offset += batch_size # Prepare for next batch

            for memory in candidate_memories_for_archive:
                memory_id = memory.get('id')
                if not memory_id:
                    logger.warning("Managed Forgetting: Found memory without ID during archival check. Skipping.")
                    continue

                mem_timestamp_str = memory.get('timestamp')
                if not mem_timestamp_str:
                    logger.warning(f"Managed Forgetting: Memory {memory_id} missing timestamp. Skipping archival check.")


                try:
                    mem_dt = datetime.fromisoformat(mem_timestamp_str.replace('Z', '+00:00'))
                    if mem_dt.tzinfo is None: # Ensure timezone aware for comparison
                        mem_dt = mem_dt.replace(tzinfo=timezone.utc)
                except ValueError:

                    logger.warning(f"Managed Forgetting: Could not parse timestamp for memory {memory_id}: {mem_timestamp_str}. Skipping archival check.")

                    continue

                is_core = memory.get('type') in self.forgetting_core_memory_types
                is_old = mem_dt < archive_before_date

                current_salience = float(memory.get('salience', 1.0) or 1.0) # Default to high salience if None

                is_low_salience = current_salience < salience_threshold_archive
                is_extremely_low_salience = current_salience < extremely_low_salience_core

                should_archive = False
                reason = ""

                if is_core:
                    if is_extremely_low_salience:
                        should_archive = True

                        reason = f"core type '{memory.get('type')}' with extremely low salience ({current_salience:.3f} < {extremely_low_salience_core})"
                else: # Not a core type
                    if is_old and is_low_salience: # Must be both old AND low salience for non-core
                        should_archive = True
                        reason = f"non-core type '{memory.get('type')}' older than {days_to_archive_default} days AND low salience ({current_salience:.3f} < {salience_threshold_archive})"
                    elif is_old and not is_low_salience: # Old but not low salience - don't archive yet based on age alone.
                        pass # logger.debug(f"Memory {memory_id} is old but salience {current_salience:.3f} is not below threshold {salience_threshold_archive}.")
                    elif is_low_salience: # Low salience but not necessarily old
                         should_archive = True
                         reason = f"non-core type '{memory.get('type')}' with low salience ({current_salience:.3f} < {salience_threshold_archive})"

                if should_archive:
                    update_success = False
                    try:
                        update_success = await asyncio.to_thread(
                            self.memory_storage.update_entry_archival_status,
                            memory_id,
                            True
                        )
                    except Exception as e_archive_update:
                         logger.error(f"Managed Forgetting: Error calling update_entry_archival_status for {memory_id}: {e_archive_update}", exc_info=True)

                    if update_success:
                        archived_count += 1
                        logger.info(f"Managed Forgetting: Archived memory ID {memory_id} ({memory.get('type')}, Sal: {current_salience:.2f}, Age: {(now - mem_dt).days}d). Reason: {reason}.")
                    else:
                        logger.warning(f"Managed Forgetting: Failed to archive memory ID {memory_id} via MemoryStorage call.")

        logger.info(f"Managed Forgetting: Archival step. Processed {processed_for_archival_count} memories. Archived {archived_count} memories.")

        # c. Update Timestamps

        self.last_forgetting_time = now
        self._save_task_last_run_time("EthosForgetting", now)
        logger.info(f"--- Ethos: Managed Forgetting Cycle Finished at {now.isoformat()} ---")

    async def run_hexus_decay(self):
        """
        Applies decay to Hexus scores, moving them towards their defined baselines.
        This method is called periodically by _periodic_hexus_decay_task.
        """
        now = datetime.now(timezone.utc)
        time_elapsed_since_last_decay = now - self.last_hexus_decay_time
        time_elapsed_seconds = time_elapsed_since_last_decay.total_seconds()

        if time_elapsed_seconds < 1.0: # Avoid too frequent calculations or if time hasn't advanced
            logger.debug(f"Hexus decay: Insufficient time ({time_elapsed_seconds:.2f}s) since last decay. Skipping.")
            return

        logger.info(f"--- Ethos: Running Hexus Decay Cycle (Time elapsed: {time_elapsed_seconds:.2f}s) ---")


        # --- Determine Current Activity ---
        current_activity_type: Optional[str] = None
        if self.chronos_engine:
            try:
                pathos_local_now = await self.get_local_datetime_for_user(PATHOS_USER_ID)
                current_activity_slot = await self.chronos_engine.get_current_activity(pathos_local_now)
                if current_activity_slot and current_activity_slot.activity_type:
                    current_activity_type = current_activity_slot.activity_type.lower() # Store as lower for easier matching
                    logger.debug(f"Hexus decay: Current activity type for Pathos: {current_activity_type}")
                else:
                    logger.debug("Hexus decay: No specific current activity found for Pathos or activity_type is None.")
            except Exception as e:
                logger.warning(f"Hexus decay: Could not get current activity for awareness: {e}", exc_info=True)
        else:
            logger.warning("Hexus decay: ChronosEngine not available. Decay will not be activity-aware.")


        # The 'hexus_decay_rate_per_cycle' from config is now superseded by per-dimension hourly rates
        # and actual time elapsed.
        # We retain hexus_decay_interval_seconds from config as the *intended* call frequency for the task.


        # Activity-aware decay - Placeholder for future enhancement.
        # The fetched current_activity_type can be used here to adjust baselines or decay rates.

        changed_scores = False
        for key, current_value in list(self.hexus_scores.items()): # Iterate over a copy if modifying
            standard_baseline = HEXUS_BASELINES.get(key)
            standard_rate_per_hour = HEXUS_DECAY_RATES.get(key)

            if standard_baseline is None:
                logger.warning(f"Hexus decay: No standard baseline defined for '{key}'. Skipping decay for this score.")
                continue
            if standard_rate_per_hour is None:
                logger.warning(f"Hexus decay: No standard hourly decay rate defined for '{key}'. Skipping decay for this score.")
                continue

            effective_baseline = standard_baseline
            effective_rate_per_hour = standard_rate_per_hour

            modifier_applied_log_msg = ""

            if current_activity_type and current_activity_type in HEXUS_ACTIVITY_MODIFIERS:
                activity_mods = HEXUS_ACTIVITY_MODIFIERS[current_activity_type]
                if key in activity_mods:
                    dimension_mods = activity_mods[key]

                    if "baseline_shift" in dimension_mods:
                        shift = dimension_mods["baseline_shift"]
                        effective_baseline += shift
                        # Clamp effective_baseline, assuming Hexus baselines are also within 0-1
                        effective_baseline = max(0.0, min(1.0, effective_baseline))
                        modifier_applied_log_msg += f" baseline_shift: {shift:+.2f} -> {effective_baseline:.2f};"

                    if "rate_multiplier" in dimension_mods:
                        multiplier = dimension_mods["rate_multiplier"]
                        effective_rate_per_hour *= multiplier
                        # Ensure rate doesn't become negative, though multipliers usually positive
                        effective_rate_per_hour = max(0.0, effective_rate_per_hour)
                        modifier_applied_log_msg += f" rate_multiplier: {multiplier:.2f} -> {effective_rate_per_hour:.3f};"

            if modifier_applied_log_msg:
                logger.debug(f"Hexus decay for '{key}' (Activity: {current_activity_type}): Modifiers applied ->{modifier_applied_log_msg}")

            # Use effective_baseline and effective_rate_per_hour in decay calculation
            decay_amount_for_cycle = (current_value - effective_baseline) * effective_rate_per_hour * (time_elapsed_seconds / 3600.0)
            new_value = current_value - decay_amount_for_cycle

            # Clamping Hexus scores (assuming all Hexus scores are 0.0 to 1.0)

            clamped_new_value = max(0.0, min(1.0, new_value))

            if abs(clamped_new_value - current_value) > 1e-4: # Only update if change is significant
                self.hexus_scores[key] = clamped_new_value
                changed_scores = True
                logger.debug(f"Hexus decay for '{key}': {current_value:.3f} -> {clamped_new_value:.3f} (baseline: {baseline:.2f}, rate/hr: {dimension_decay_rate_per_hour:.3f}, dt: {time_elapsed_seconds:.0f}s). Change: {decay_amount_for_cycle:+.4f}")

        if changed_scores:
            self._save_hexus_scores()
            logger.info(f"Hexus scores updated and saved after decay. Current scores: { {k: round(v, 3) for k,v in self.hexus_scores.items()} }")
        else:
            logger.info("Hexus decay cycle: No significant changes to Hexus scores this cycle.")

        self.last_hexus_decay_time = now
        self._save_task_last_run_time("HexusDecay", now)
        logger.info(f"--- Ethos: Hexus Decay Cycle Finished (Duration processed: {time_elapsed_seconds:.2f}s) ---")

    async def _get_memories_for_reflection(self, lookback_days: int, query_limit: int) -> List[MemoryEntry]:
        """
        Fetches a broad range of memories within a given lookback period for reflection.
        """
        if not self.memory_storage:
            logger.error("EthosCore: MemoryStorage not available. Cannot fetch memories for reflection.")
            return []

        now_utc = datetime.now(timezone.utc)
        start_time_dt = now_utc - timedelta(days=lookback_days)

        relevant_memory_types = [
            'chat_interaction',
            'firmament_activity_log',
            'feedback',
            'received_subconscious_intention',
            'npc_dialogue_event',
            'learned_correction',
            'reflection_insight', # Include past insights
            'aspiration',         # Pathos's own aspirations
            'world_knowledge'     # Recently acquired/verified world knowledge
        ]

        logger.debug(f"EthosCore: Fetching memories for reflection. Lookback: {lookback_days} days (from {start_time_dt.isoformat()}), Limit: {query_limit}, Types: {relevant_memory_types}")

        try:
            # Using PATHOS_USER_ID to get Pathos's own experiences and general knowledge.
            # Specific user interactions are part of 'chat_interaction' and will be included if they involve PATHOS_USER_ID (implicitly handled by how they are stored).
            # The MemoryStorage method get_memories_by_time_range_and_types should ideally handle user_id filtering if applicable for each type.
            # For reflection, we are primarily interested in Pathos's own cognitive stream and direct experiences.

            # Changed to get_memories_for_summary, removed sort_by_salience_then_recency
            fetched_memories = await self.memory_storage.get_memories_for_summary(
                user_id=PATHOS_USER_ID, # Focus on Pathos's own context for self-reflection
                start_time_utc=start_time_dt,
                end_time_utc=now_utc,
                types=relevant_memory_types,
                limit=query_limit
                # include_archived defaults to False, which is fine here

            )
            logger.info(f"EthosCore: Fetched {len(fetched_memories)} memories for reflection.")
            return fetched_memories
        except Exception as e:
            logger.error(f"EthosCore: Error fetching memories for reflection: {e}", exc_info=True)
            return []

    async def get_background_tasks(self) -> List[asyncio.Task]:
        """Create and return background tasks for EthosCore operations."""
        tasks = []
        
        # Create background task for reflection cycle
        reflection_task = asyncio.create_task(
            self._periodic_reflection_task(),
            name="EthosReflectionTask"
        )
        tasks.append(reflection_task)
        
        # Create background task for managed forgetting
        if self.config.ENABLE_MANAGED_FORGETTING:
            forgetting_task = asyncio.create_task(
                self._periodic_forgetting_task(),
                name="EthosForgettingTask"
            )
            tasks.append(forgetting_task)
        
        # Create background task for hexus decay
        hexus_task = asyncio.create_task(
            self._periodic_hexus_decay_task(),
            name="EthosHexusDecayTask"
        )
        tasks.append(hexus_task)

        # Create background task for Firmament simulation loop
        if self.firmament_module and self.config.get_firmament_module_config().get("enable_firmament"):
            logger.info("EthosCore: Adding Firmament simulation loop to background tasks.")
            firmament_task = asyncio.create_task(
                self._firmament_simulation_loop(),
                name="FirmamentSimulationLoopTask"
            )
            tasks.append(firmament_task)
        elif self.firmament_module:
            logger.info("EthosCore: FirmamentModule present but disabled by configuration. Simulation loop not started.")
        
        # Add Long-Term Planning Task
        planning_interval = self.ethos_config.get('long_term_planning_interval_seconds', 86400.0 * 3)
        if planning_interval > 0 :
             tasks.append(asyncio.create_task(self._periodic_long_term_planning_task(), name="PathosLongTermPlanningTask"))
        else:
            logger.info("Long-term planning task disabled due to interval <= 0.")

            logger.info(f"EthosCore created {len(tasks)} background tasks")
        return tasks

    async def _periodic_knowledge_upkeep_task(self):
        """Periodic task for running knowledge upkeep cycles."""
        knowledge_upkeep_interval = self.ethos_config.get('knowledge_upkeep_interval_seconds', 86400)
        if knowledge_upkeep_interval <= 0:
            logger.info("Knowledge upkeep periodic task disabled due to interval <= 0.")
            return # Do not run if interval is zero or negative

        while True:
            try:
                now = datetime.now(timezone.utc)
                time_since_last = (now - self.last_knowledge_upkeep_time).total_seconds()

                if time_since_last >= knowledge_upkeep_interval:
                    await self.run_knowledge_upkeep()
                else:
                    # Sleep until next scheduled time
                    sleep_time = knowledge_upkeep_interval - time_since_last
                    await asyncio.sleep(min(sleep_time, 3600))  # Check at least every hour
            except asyncio.CancelledError:
                logger.info("EthosCore knowledge upkeep task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in knowledge upkeep task: {e}", exc_info=True)
                await asyncio.sleep(300)  # Wait 5 minutes before retrying after an error

    async def _firmament_simulation_loop(self):
        """Dedicated loop for Firmament simulation ticks."""
        if not self.firmament_module: # Should not happen if task is started correctly
            logger.error("EthosCore: Firmament module not set, cannot start simulation loop.")
            return

        fm_config = self.config.get_firmament_module_config()
        # Use the new tick_interval_seconds from FirmamentModuleConfig
        tick_interval = fm_config.get("simulation_tick_interval_seconds", 60.0)
        logger.info(f"EthosCore: Starting Firmament simulation loop with tick interval: {tick_interval}s.")

        while True:
            try:
                await self.firmament_module.run_simulation_tick()
                await asyncio.sleep(tick_interval)
            except asyncio.CancelledError:
                logger.info("EthosCore: Firmament simulation loop cancelled.")
                break
            except Exception as e:
                logger.error(f"EthosCore: Error in Firmament simulation loop: {e}", exc_info=True)
                # Decide on backoff strategy or continue after a delay
                await asyncio.sleep(tick_interval * 2) # Wait longer after an error


    async def _periodic_reflection_task(self):
        """Periodic task for running reflection cycles."""
        reflection_interval = self.ethos_config.get('reflection_interval_seconds', 86400.0)
        while True:
            try:
                now = datetime.now(timezone.utc)
                time_since_last = (now - self.last_reflection_time).total_seconds()
                
                if time_since_last >= reflection_interval:
                    await self.run_reflection_cycle()
                else:
                    # Sleep until next reflection time
                    sleep_time = reflection_interval - time_since_last
                    await asyncio.sleep(min(sleep_time, 3600))  # Check at least every hour
            except asyncio.CancelledError:
                logger.info("EthosCore reflection task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in reflection task: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait before retrying

    async def _periodic_forgetting_task(self):
        """Periodic task for running managed forgetting cycles."""
        forgetting_interval = self.ethos_config.get('forgetting_interval_seconds', 43200.0)
        while True:
            try:
                now = datetime.now(timezone.utc)
                time_since_last = (now - self.last_forgetting_time).total_seconds()
                
                if time_since_last >= forgetting_interval:
                    await self.run_managed_forgetting()
                else:
                    # Sleep until next forgetting time
                    sleep_time = forgetting_interval - time_since_last
                    await asyncio.sleep(min(sleep_time, 3600))  # Check at least every hour
            except asyncio.CancelledError:
                logger.info("EthosCore forgetting task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in forgetting task: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait before retrying

    async def _periodic_hexus_decay_task(self):
        """Periodic task for running hexus decay cycles."""
        hexus_decay_interval = self.ethos_config.get('hexus_decay_interval_seconds', 3600.0)
        while True:
            try:
                now = datetime.now(timezone.utc)
                time_since_last = (now - self.last_hexus_decay_time).total_seconds()
                
                if time_since_last >= hexus_decay_interval:
                    await self.run_hexus_decay()
                else:
                    # Sleep until next decay time
                    sleep_time = hexus_decay_interval - time_since_last
                    await asyncio.sleep(min(sleep_time, 1800))  # Check at least every 30 minutes
            except asyncio.CancelledError:
                logger.info("EthosCore hexus decay task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in hexus decay task: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait before retrying

    async def _periodic_long_term_planning_task(self):
        """Periodic task for running long-term planning cycles."""
        # Default to 3 days if not specified
        planning_interval = self.ethos_config.get('long_term_planning_interval_seconds', 86400.0 * 3)
        if planning_interval <= 0:
            logger.info("Long-term planning periodic task disabled due to interval <= 0.")
            return # Do not run if interval is zero or negative

        while True:
            try:
                now = datetime.now(timezone.utc)
                time_since_last = (now - self.last_long_term_planning_time).total_seconds()

                if time_since_last >= planning_interval:
                    await self.run_long_term_planning()
                    # self.run_long_term_planning() already updates self.last_long_term_planning_time
                    # and saves it via _save_task_last_run_time
                else:
                    # Sleep until next scheduled time
                    sleep_time = planning_interval - time_since_last
                    await asyncio.sleep(min(sleep_time, 3600))  # Check at least every hour
            except asyncio.CancelledError:
                logger.info("EthosCore long-term planning task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in long-term planning task: {e}", exc_info=True)
                await asyncio.sleep(300)  # Wait 5 minutes before retrying after an error

    async def generate_daily_experiential_summary(self, user_id: str = PATHOS_USER_ID) -> str:
        '''
        Generates a narrative summary of Pathos's experiences over the lookback period,
        suitable for seeding dreams in the subconscious_node.
        '''
        default_summary = "Pathos experienced a day of various activities and thoughts."
        if not self.ethos_config.get("enable_memory_summarization", True): # Default to True if not specified
            logger.info("EthosCore: Memory summarization for daily dream seed is disabled by EthosConfig.enable_memory_summarization.")
            return default_summary

        summarization_llm_role = self.ethos_config.get("summarization_llm_role", "LOGOS_TECHNE")
        llm_config = self.config.get_llm_config(summarization_llm_role)

        if not llm_config or not llm_config.get("url"):
            logger.error(f"EthosCore: Summarization LLM role '{summarization_llm_role}' not configured or URL missing. Cannot generate daily summary.")
            return default_summary

        if not self.logos_core: # LogosCore is used for the actual LLM call
            logger.error("EthosCore: LogosCore not available. Cannot make LLM call for daily summary.")
            return default_summary

        try:
            # Get parameters from config
            lookback_hours = self.ethos_config.get("daily_summary_lookback_hours", 18)
            max_memories_to_fetch = self.ethos_config.get("daily_summary_max_memories", 30)

            # 1. Determine Time Range
            pathos_home_tz_str = self.ethos_config.get("pathos_home_timezone", "UTC")
            try:
                pathos_home_tz = pytz.timezone(pathos_home_tz_str)
            except pytz.UnknownTimeZoneError:
                logger.warning(f"EthosCore: Unknown timezone '{pathos_home_tz_str}' in config. Defaulting to UTC for daily summary.")
                pathos_home_tz = pytz.utc

            # Get Pathos's current local time via the existing EthosCore method
            # This method already handles timezone conversion.
            end_dt_pathos_local = await self.get_local_datetime_for_user(user_id)
            if not end_dt_pathos_local:
                logger.error("EthosCore: Could not determine Pathos's current local time for daily summary. Using UTC now.")
                end_dt_pathos_local = datetime.now(timezone.utc) # Fallback to UTC now

            start_dt_pathos_local = end_dt_pathos_local - timedelta(hours=lookback_hours)

            logger.info(f"EthosCore: Generating daily summary for period: {start_dt_pathos_local.isoformat()} to {end_dt_pathos_local.isoformat()} (Pathos Local Time)")

            # 2. Retrieve Memories
            memory_types_for_summary = [
                'interaction', 'firmament_activity_log', 'received_subconscious_intention',
                'npc_dialogue_event', 'dream_narrative_from_node', # include last night's dream
                'user_fact', 'world_knowledge' # recently learned things
            ]
            # get_memories_by_time_range_and_types needs start/end in UTC if DB stores UTC
            # Assuming get_local_datetime_for_user returns tz-aware, convert to UTC for DB query
            start_dt_utc = start_dt_pathos_local.astimezone(timezone.utc)
            end_dt_utc = end_dt_pathos_local.astimezone(timezone.utc)

            # Assuming MemoryStorage will have this method or an equivalent that can handle datetime objects
            # and type filtering. If it expects strings, isoformat() conversion will be needed here.
            # For now, coding as per the assumption it can handle datetime objects.
            recent_memories = await self.memory_storage.get_memories_by_time_range_and_types(
                user_id=user_id,
                start_time=start_dt_utc,
                end_time=end_dt_utc,
                types=memory_types_for_summary,
                limit=max_memories_to_fetch,
                sort_by_salience_then_recency=True # Assumes MemoryStorage method supports this
            )

            if not recent_memories:
                logger.info("EthosCore: No significant memories found in the lookback period for daily summary.")
                return "Pathos's day seemed quiet, with few distinct events or thoughts recorded."

            # 3. Format Memories for Prompt
            formatted_memories_for_prompt = []
            for mem in recent_memories:
                try:
                    # Convert UTC timestamp from memory back to Pathos's local time for display in prompt
                    mem_ts_utc = datetime.fromisoformat(mem.get('timestamp', '').replace("Z", "+00:00")).replace(tzinfo=timezone.utc)
                    mem_ts_local = mem_ts_utc.astimezone(pathos_home_tz)
                    time_str = mem_ts_local.strftime("%H:%M")
                    # Shorten content, especially for logs or long interactions
                    content_snippet = mem.get('content', '')
                    if len(content_snippet) > 100: content_snippet = content_snippet[:97] + "..."
                    formatted_memories_for_prompt.append(f"- {time_str} ({mem.get('type')}): {content_snippet}")
                except ValueError: # Catch errors from fromisoformat or strftime
                    formatted_memories_for_prompt.append(f"- ({mem.get('type')}): {mem.get('content', '')[:100]}...")

            memory_text_for_prompt = "\n".join(formatted_memories_for_prompt)

            # 4. Fetch Current Mood
            current_mood = self.get_current_mood() # This is synchronous
            mood_summary_for_prompt = f"His overall mood state towards the end of this period was: {current_mood.get('name', 'neutral')} (Valence: {current_mood.get('valence',0):.2f}, Arousal: {current_mood.get('arousal',0):.2f})."

            # 5. Construct LLM Prompt
            system_prompt = (
                "You are tasked with creating a brief, narrative summary of Pathos's day based on selected memories and his mood. "
                "This summary will be used to seed his subconscious dream engine. Focus on key events, significant interactions, "
                "strong emotional shifts, important thoughts, or new learnings. "
                "Weave these elements into a short story (1-2 paragraphs, max 150-200 words). "
                "Be evocative and reflective, capturing the essence of his experiences. Do not just list memories."
            )
            user_prompt = (
                f"Here are selected memories from Pathos's experiences over the last {lookback_hours} hours (times are Pathos's local time {pathos_home_tz_str}):\n"
                f"{memory_text_for_prompt}\n\n"
                f"{mood_summary_for_prompt}\n\n"
                "Please provide the narrative summary of Pathos's day:"
            )
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

            # 6. LLM Call via LogosCore (assuming _call_llm_client_directly exists and is suitable)
            # The _call_llm_client_directly method in LogosCore returns a Dict, we need the text content.
            llm_response_dict = await self.logos_core._call_llm_client_directly(
                llm_config=llm_config,
                messages=messages,
                max_tokens_override=300 # Allow enough tokens for a couple of paragraphs
            )

            if llm_response_dict and llm_response_dict.get("content"):
                summary_text = str(llm_response_dict["content"]).strip()
                logger.info(f"EthosCore: Successfully generated daily summary: '{summary_text[:100]}...'")
                return summary_text
            else:
                logger.error(f"EthosCore: Daily summary generation LLM call did not return valid content. Response: {llm_response_dict}")
                return default_summary

        except Exception as e:
            logger.error(f"EthosCore: Error generating daily experiential summary: {e}", exc_info=True)
            return default_summary

    async def chronos_bridge_add_event(self, title: str, start_date_str: str, end_date_str: str, event_type_str: str, description: Optional[str], location: Optional[str], activity_theme: Optional[str], planned_sites_or_tasks: Optional[List[str]], user_id_for_event: str) -> Optional[str]:
        if not self.chronos_engine:
            logger.error("ChronosEngine not available in EthosCore to add event.")
            return None
        try:
            event_data = {
                "title": title, "start_date": start_date_str, "end_date": end_date_str,
                "event_type": event_type_str, "description": description, "location": location,
                "details": {"activity_theme": activity_theme, "planned_sites_or_tasks": planned_sites_or_tasks},
                "user_id": user_id_for_event # This should be PATHOS_USER_ID if Pathos is scheduling for himself
            }
            added_event = await self.chronos_engine.add_planned_event(event_data)
            return added_event.id if added_event else None
        except Exception as e:
            logger.error(f"Error in chronos_bridge_add_event: {e}", exc_info=True)
            return None
            
    def get_current_mood(self) -> Dict[str, Any]:

        """
        Derives a simplified valence/arousal representation from Hexus scores.
        Also includes all Hexus scores for more detailed context if needed.
        Returns a dictionary that includes 'valence', 'arousal', 'name' (derived),
        and a 'hexus_snapshot' of all current Hexus scores.
        """
        if not self.config.ENABLE_MOOD_SIMULATION: # Keep this check if Hexus is part of mood simulation
            return {"valence": 0.0, "arousal": 0.0, "name": "neutral", "simulation_disabled": True, "hexus_snapshot": self.hexus_scores.copy()}

        # Simple derivation:
        # Valence: influenced by joy, contentment vs. stress, resentment, melancholy
        # Arousal: influenced by curiosity, focus, ambition, impulsiveness vs. tiredness

        joy_val = self.hexus_scores.get("joy", 0.0)
        contentment_val = self.hexus_scores.get("contentment", 0.0)
        stress_val = self.hexus_scores.get("stress", 0.0)
        resentment_val = self.hexus_scores.get("resentment", 0.0)
        melancholy_val = self.hexus_scores.get("melancholy", 0.0)

        curiosity_val = self.hexus_scores.get("curiosity", 0.0)
        focus_val = self.hexus_scores.get("focus", 0.0)
        ambition_val = self.hexus_scores.get("ambition", 0.0)
        impulsiveness_val = self.hexus_scores.get("impulsiveness", 0.0)
        tiredness_val = self.hexus_scores.get("tiredness", 0.0)

        derived_valence = (joy_val + contentment_val) - (stress_val + resentment_val + melancholy_val)
        derived_arousal = (curiosity_val + focus_val + ambition_val + impulsiveness_val) / 2.0 - tiredness_val

        # Clamp derived valence/arousal to -1.0 to 1.0 for consistency if used by other systems expecting that range.
        derived_valence = max(-1.0, min(1.0, derived_valence))
        derived_arousal = max(-1.0, min(1.0, derived_arousal))

        # Determine a qualitative name (simplified)
        mood_name = "neutral"
        if derived_valence > 0.3:
            if derived_arousal > 0.3: mood_name = "excited"
            else: mood_name = "pleased"
        elif derived_valence < -0.3:
            if derived_arousal > 0.3: mood_name = "agitated"
            else: mood_name = "displeased"
        elif derived_arousal > 0.5: mood_name = "engaged"
        elif derived_arousal < -0.5: mood_name = "calm"


        return {
            "valence": derived_valence,
            "arousal": derived_arousal,
            "name": mood_name, # Simplified qualitative name
            "simulation_disabled": False, # Assuming if this runs, simulation is enabled
            "hexus_snapshot": self.hexus_scores.copy() # Include all current Hexus scores
        }

    async def process_event_for_hexus_update(self, event_type: str, payload: Optional[Dict[str, Any]] = None, magnitude_multiplier: float = 1.0):
        """
        Updates Hexus scores based on various system or feedback events.
        Uses the HEXUS_EVENT_DEFINITIONS mapping.
        """
        if not self.config.ENABLE_MOOD_SIMULATION: # Assuming Hexus updates are tied to this flag
            return

        logger.debug(f"Processing Hexus event: '{event_type}' with magnitude multiplier: {magnitude_multiplier}")

        event_definition = None
        # Prioritize subjective reaction definitions
        if event_type in HEXUS_SUBJECTIVE_REACTION_DEFINITIONS:
            event_definition = HEXUS_SUBJECTIVE_REACTION_DEFINITIONS[event_type]
            logger.debug(f"Found Hexus event '{event_type}' in HEXUS_SUBJECTIVE_REACTION_DEFINITIONS.")
        elif event_type in HEXUS_EVENT_DEFINITIONS: # Fallback to direct event definitions
            event_definition = HEXUS_EVENT_DEFINITIONS[event_type]
            logger.debug(f"Found Hexus event '{event_type}' in HEXUS_EVENT_DEFINITIONS.")

        if not event_definition: # If event_definition is an empty dict (like for REACTION_INDIFFERENT_UNEFFECTED), it's valid.
            if event_definition is None: # Only warn if not found in either and not intentionally empty
                 logger.warning(f"Hexus event '{event_type}' not found in subjective or direct definitions.")
            else: # It was an empty dict, meaning no Hexus change intended
                 logger.debug(f"Hexus event '{event_type}' is defined as no-op (empty definition). No Hexus scores changed.")
            return

        reason_for_change = f"event: {event_type}"

        if payload: # Optionally include payload summary in reason for more detailed logging
            payload_summary = {k: (str(v)[:30] + '...' if isinstance(v, str) and len(v) > 30 else v) for k,v in payload.items()}
            reason_for_change += f" (payload: {payload_summary})"


        for dimension, delta in event_definition.items():
            self._apply_hexus_change(dimension, delta * magnitude_multiplier, reason_for_change)
        
        # Specific handling for feedback event to extract more detailed reason if needed

        if event_type == "USER_FEEDBACK_CORRECTION" and payload and payload.get('text'):

             self._apply_hexus_change('stress', HEXUS_EVENT_DEFINITIONS["USER_FEEDBACK_CORRECTION"].get('stress',0.03) * magnitude_multiplier, f"initial reaction to correction text: {payload.get('text','')[:30]}...")


    async def retrieve_relevant_past_interactions(
        self,
        query_text: str,
        user_id: str,
        current_history_entry_ids: List[str], # IDs of MemoryEntry objects already in the standard recent history
        top_k: int,
        similarity_threshold: float
    ) -> List[MemoryEntry]:
        """
        Retrieves relevant past chat interactions based on similarity to the query_text,
        excluding entries already present in the current recent history.
        """
        logger.info(f"Retrieving relevant past interactions for user '{user_id}' with query '{query_text[:50]}...'. Excluding {len(current_history_entry_ids)} current IDs. Top_k={top_k}, Threshold={similarity_threshold}")

        if not query_text or not user_id:
            return []

        # Fetch more candidates than top_k to allow for filtering
        # The +5 is a small buffer. Consider if memory_storage.find_similar's internal limit (e.g. 500) is sufficient.
        fetch_k = top_k + len(current_history_entry_ids) + 10

        # Call memory_storage.find_similar()
        # Assuming 'interaction' is the correct type for past conversation turns.
        # The find_similar method in MemoryStorage already filters out 'pending_context_document' and 'chat_storage'.
        try:
            # find_similar returns List[Tuple[float, MemoryEntry]]
            similar_results_with_scores = self.memory_storage.find_similar(
                query_text=query_text,
                top_k=fetch_k, # Fetch more to filter
                allowed_types=['interaction'], # Specify that we only want 'interaction' type memories
                threshold=similarity_threshold # Use the provided threshold
            )
        except Exception as e:
            logger.error(f"Error calling memory_storage.find_similar: {e}", exc_info=True)
            return []

        if not similar_results_with_scores:
            logger.debug(f"No similar past interactions found by memory_storage.find_similar for user '{user_id}'.")
            return []

        # Filter results in Python
        valid_candidates: List[MemoryEntry] = []
        processed_ids = set(current_history_entry_ids) # Keep track of IDs to ensure uniqueness after filtering

        for score, mem_entry in similar_results_with_scores:
            entry_id = mem_entry.get('id')
            if not entry_id or entry_id in processed_ids:
                logger.debug(f"Skipping entry ID {entry_id}: already processed or in current history.")
                continue

            # Ensure the user_id in the metadata matches the input user_id
            # This is crucial if find_similar doesn't filter by user_id in its SQL for 'interaction' type.
            # MemoryStorage.find_similar has a user_id_context param but it's for prioritizing, not strict filtering for all types.
            metadata_user_id = mem_entry.get('metadata', {}).get('user_id')
            if metadata_user_id != user_id:
                logger.debug(f"Skipping entry ID {entry_id}: metadata user_id '{metadata_user_id}' does not match requested user_id '{user_id}'.")
                continue

            # Add score to metadata if not already there, for potential later use, though not strictly needed by PromptBuilder currently
            if 'similarity_score' not in mem_entry.get('metadata', {}): # Avoid overwriting if somehow already there
                 mem_entry.setdefault('metadata', {})['similarity_score'] = score

            valid_candidates.append(mem_entry)
            processed_ids.add(entry_id) # Add to processed to ensure it's not picked again if somehow duplicated in find_similar results

        # Sort by similarity score (descending) - find_similar already does this, but if we combined lists, re-sorting might be needed.
        # Here, find_similar already sorts, so this is more for ensuring contract if logic changed.
        # valid_candidates.sort(key=lambda x: x.get('metadata', {}).get('similarity_score', 0.0), reverse=True)
        # No need to re-sort if find_similar's output order is trusted for the filtered set.

        final_selection = valid_candidates[:top_k]

        logger.info(f"Retrieved {len(final_selection)} relevant past interactions for user '{user_id}' after filtering. (Initial candidates: {len(similar_results_with_scores)}, Valid after filters: {len(valid_candidates)})")
        return final_selection