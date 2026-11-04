"""Compatibility import for :mod:`openrsi_space.integrations.dungeness.agent`; new callers use that module."""
import sys
from openrsi_space.integrations.dungeness import agent as _implementation

sys.modules[__name__] = _implementation
