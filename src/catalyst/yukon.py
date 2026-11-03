"""Compatibility import for :mod:`catalyst.integrations.yukon.authentication`; new callers use that module."""
import sys
from catalyst.integrations.yukon import authentication as _implementation

sys.modules[__name__] = _implementation
