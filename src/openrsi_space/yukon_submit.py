"""Compatibility import for :mod:`openrsi_space.integrations.yukon.submission`; new callers use that module."""
import sys
from openrsi_space.integrations.yukon import submission as _implementation

sys.modules[__name__] = _implementation
