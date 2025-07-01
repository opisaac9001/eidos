import logging # Moved import to top
"""
Core Persona Logic for Eidos Agent.

This package contains modules defining Pathos's core being and operational logic,
including:
- Ethos (self, memory, values)
- Logos (reasoning, knowledge integration)
- Chronos (time, scheduling, event management)
- Oneiros (dreaming, subconscious processing)
"""
# This __init__.py can also be used to control imports from the persona_logic package.
# For example:
# from .ethos_core import EthosCore
# from .logos_core import LogosCore
# from .chronos_engine import ChronosEngine
# from .oneiros_module import OneirosModule

logger = logging.getLogger(__name__)
logger.info("eidos_agent.persona_logic package loaded.")
