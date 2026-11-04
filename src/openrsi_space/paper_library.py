"""Compatibility import for :mod:`openrsi_space.challenge.papers`.

Keep one module object so existing consumers and patched configuration use the
same implementation. New code should import openrsi_space.challenge.papers.
"""
import sys
from openrsi_space.challenge import papers as _implementation

sys.modules[__name__] = _implementation
