"""Compatibility import for :mod:`openrsi_space.integrations.yukon.authentication`; new callers use that module."""
import sys
from openrsi_space.integrations.yukon import authentication as _implementation

sys.modules[__name__] = _implementation
