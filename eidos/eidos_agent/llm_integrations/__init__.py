# eidos_agent/llm_integrations/__init__.py
"""
Modules responsible for direct LLM interactions, prompt construction,
tool definitions, and tool orchestration for Pathos.
"""
import logging # Added import for logger

# Attempt to import and re-export key classes.
# These will only work once the files are moved in subsequent steps.
try:
    from .pathos_interface import PathosInterface
except ImportError: # pragma: no cover
    pass

try:
    from .llm_client import LLMClient
except ImportError: # pragma: no cover
    pass

try:
    from .prompt_builder import PromptBuilder
except ImportError: # pragma: no cover
    pass

try:
    from .tool_orchestrator import ToolOrchestrator
except ImportError: # pragma: no cover
    pass

# pathos_tools_definitions.py is usually imported directly by other modules here,
# but re-exporting its lists could be an option if desired.
# For now, assume direct import of its constants.

logger = logging.getLogger(__name__)
logger.info("eidos_agent.llm_integrations package loaded.")
