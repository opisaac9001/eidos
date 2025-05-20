# eidos_agent/modules/logos_core/__init__.py

"""
Initializes the Logos Core module.

This primarily makes the LogosCore class available for import 
from the eidos_agent.modules.logos_core package.
"""

from .handler import LogosCore

# Optionally, you could define __all__ if you want to be explicit
# about what is exported when someone does 'from eidos_agent.modules.logos_core import *'
# __all__ = ["LogosCore"]