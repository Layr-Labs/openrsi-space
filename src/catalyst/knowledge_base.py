"""Compatibility import for :mod:`catalyst.challenge.resources`.

Keep one module object so existing consumers and patched configuration use the
same implementation. New code should import catalyst.challenge.resources.
"""
import sys
from catalyst.challenge import resources as _implementation

sys.modules[__name__] = _implementation
