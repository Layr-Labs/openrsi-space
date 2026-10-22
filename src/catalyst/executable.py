"""Compatibility import for :mod:`catalyst.harnesses.executable`; new callers use that module."""
import sys
from catalyst.harnesses import executable as _implementation

sys.modules[__name__] = _implementation
