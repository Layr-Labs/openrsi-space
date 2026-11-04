"""Compatibility import for :mod:`openrsi_space.integrations.dungeness.runtime_contract`; new callers use that module."""
import sys
from openrsi_space.integrations.dungeness import runtime_contract as _implementation

sys.modules[__name__] = _implementation
