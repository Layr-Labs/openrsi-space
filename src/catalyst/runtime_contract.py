"""Compatibility import for :mod:`catalyst.integrations.dungeness.runtime_contract`; new callers use that module."""
import sys
from catalyst.integrations.dungeness import runtime_contract as _implementation

sys.modules[__name__] = _implementation
