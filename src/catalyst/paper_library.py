"""Compatibility import for catalyst.challenge.papers."""
import sys
from catalyst.challenge import papers as _implementation
sys.modules[__name__] = _implementation
