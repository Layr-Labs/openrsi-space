"""Compatibility import for :mod:`catalyst.integrations.yukon.submission`; new callers use that module."""
import sys
from catalyst.integrations.yukon import submission as _implementation

sys.modules[__name__] = _implementation
