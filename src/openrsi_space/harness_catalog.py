"""Compatibility import for :mod:`openrsi_space.client.catalog`; new callers use that module."""
import sys
from openrsi_space.client import catalog as _implementation

sys.modules[__name__] = _implementation
