"""Compatibility import for :mod:`openrsi_space.integrations.yukon.receipts`; new callers use that module."""
import sys
from openrsi_space.integrations.yukon import receipts as _implementation

sys.modules[__name__] = _implementation
