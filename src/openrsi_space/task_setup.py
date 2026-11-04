"""Compatibility import for :mod:`openrsi_space.challenge.preparation`.

Keep one module object so existing consumers and patched configuration use the
same implementation. New code should import openrsi_space.challenge.preparation.
"""
import sys
from openrsi_space.challenge import preparation as _implementation

sys.modules[__name__] = _implementation
