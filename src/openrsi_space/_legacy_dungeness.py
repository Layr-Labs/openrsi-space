"""Compatibility import for :mod:`openrsi_space.integrations.dungeness.legacy`; new callers use that module."""
import sys
from openrsi_space.integrations.dungeness import legacy as _implementation

sys.modules[__name__] = _implementation
