"""Compatibility import for :mod:`openrsi_space.challenge.catalog`.

Keep one module object so existing consumers and patched configuration use the
same implementation. New code should import openrsi_space.challenge.catalog.
"""
import sys
from openrsi_space.challenge import catalog as _implementation

sys.modules[__name__] = _implementation
