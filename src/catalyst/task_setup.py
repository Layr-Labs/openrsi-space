"""Compatibility import for :mod:`catalyst.challenge.preparation`.

Keep one module object so existing consumers and patched configuration use the
same implementation. New code should import catalyst.challenge.preparation.
"""
import sys
from catalyst.challenge import preparation as _implementation

sys.modules[__name__] = _implementation
