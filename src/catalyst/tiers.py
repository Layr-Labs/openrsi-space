"""Compatibility import for :mod:`catalyst.contracts.accounting`; new callers use that module."""
import sys
from catalyst.contracts import accounting as _implementation

sys.modules[__name__] = _implementation
