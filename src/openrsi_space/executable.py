"""Compatibility import for :mod:`openrsi_space.harnesses.executable`; new callers use that module."""
import sys
from openrsi_space.harnesses import executable as _implementation

sys.modules[__name__] = _implementation
