"""Compatibility import for :mod:`catalyst.integrations.dungeness.legacy`; new callers use that module."""
import sys
from catalyst.integrations.dungeness import legacy as _implementation

sys.modules[__name__] = _implementation
