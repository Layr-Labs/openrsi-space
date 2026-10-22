"""Compatibility import for :mod:`catalyst.integrations.dungeness.local`; new callers use that module."""
import sys
from catalyst.integrations.dungeness import local as _implementation

sys.modules[__name__] = _implementation
