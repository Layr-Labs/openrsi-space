"""Compatibility import for :mod:`openrsi_space.integrations.dungeness.local`; new callers use that module."""
import sys
from openrsi_space.integrations.dungeness import local as _implementation

sys.modules[__name__] = _implementation
