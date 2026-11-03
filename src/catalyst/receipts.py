"""Compatibility import for :mod:`catalyst.integrations.yukon.receipts`; new callers use that module."""
import sys
from catalyst.integrations.yukon import receipts as _implementation

sys.modules[__name__] = _implementation
