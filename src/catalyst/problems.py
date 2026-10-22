"""Compatibility import for :mod:`catalyst.challenge.catalog`.

Keep one module object so existing consumers and patched configuration use the
same implementation. New code should import catalyst.challenge.catalog.
"""
import sys
from catalyst.challenge import catalog as _implementation

sys.modules[__name__] = _implementation
