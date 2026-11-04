"""Compatibility import for :mod:`openrsi_space.contracts.accounting`; new callers use that module."""
import sys
from openrsi_space.contracts import accounting as _implementation

sys.modules[__name__] = _implementation
