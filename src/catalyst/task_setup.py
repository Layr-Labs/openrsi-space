"""Compatibility import for catalyst.challenge.preparation."""
import sys
from catalyst.challenge import preparation as _implementation
sys.modules[__name__] = _implementation
