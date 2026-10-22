"""Compatibility import for :mod:`catalyst.challenge.assets`.

Keep one module object so existing consumers and patched configuration use the
same implementation. New code should import catalyst.challenge.assets.
"""
import sys
from catalyst.challenge import assets as _implementation

sys.modules[__name__] = _implementation
