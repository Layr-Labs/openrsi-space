"""Compatibility import for :mod:`catalyst.challenge.papers`.

Keep one module object so existing consumers and patched configuration use the
same implementation. New code should import catalyst.challenge.papers.
"""
import sys
from catalyst.challenge import papers as _implementation

sys.modules[__name__] = _implementation
