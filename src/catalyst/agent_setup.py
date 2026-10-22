"""Compatibility import for :mod:`catalyst.integrations.dungeness.agent`; new callers use that module."""
import sys
from catalyst.integrations.dungeness import agent as _implementation

sys.modules[__name__] = _implementation
