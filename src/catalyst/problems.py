"""Compatibility import for catalyst.challenge.catalog."""
import sys
from catalyst.challenge import catalog as _implementation
sys.modules[__name__] = _implementation
