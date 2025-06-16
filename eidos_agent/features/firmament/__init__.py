# eidos_agent/features/firmament/__init__.py
"""
The Firmament module, responsible for world simulation, event processing,
and managing Pathos's interaction with his environment.
This module uses an event-driven architecture.
"""
import logging

logger = logging.getLogger(__name__)
logger.info("eidos_agent.features.firmament package loaded with new event-driven structure.")

# Key components of the new Firmament module can be imported directly
# from their respective submodules, for example:
# from eidos_agent.features.firmament.core.event_bus import EventBus
# from eidos_agent.features.firmament.core.simulator import run_simulation_tick
# from eidos_agent.features.firmament.core.event_types import *
#
# For now, no components are re-exported at this package level to encourage
# explicit imports from submodules.
