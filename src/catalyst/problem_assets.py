"""Compatibility import for catalyst.challenge.assets."""
import sys
from catalyst.challenge import assets as _implementation
sys.modules[__name__] = _implementation
