# eidos_agent/persona_logic/chronos_engine/__init__.py
"""Pathos's internal sense of time, scheduling, and event management."""
from .engine import ChronosEngine, PATHOS_USER_ID
from .models import ActivitySlot, PathosEvent, ActivitySlotDetails, PathosEventDetails, ActivityType, EventType

import logging # Added import for logger
logger = logging.getLogger(__name__)
logger.info("eidos_agent.persona_logic.chronos_engine package loaded and exports configured.")
