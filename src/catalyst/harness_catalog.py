"""Compatibility import for :mod:`catalyst.client.catalog`; new callers use that module."""
import sys
from catalyst.client import catalog as _implementation

sys.modules[__name__] = _implementation
