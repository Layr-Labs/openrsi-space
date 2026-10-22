"""Forward legacy module attributes to their canonical owners during migration."""
import sys
from types import ModuleType


class _ForwardingModule(ModuleType):
    def __getattr__(self, name):
        owner = self._owners.get(name)
        if owner is None:
            raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")
        return getattr(owner, name)

    def __setattr__(self, name, value):
        owner = self.__dict__.get("_owners", {}).get(name)
        if owner is None:
            super().__setattr__(name, value)
        else:
            setattr(owner, name, value)

    def __delattr__(self, name):
        owner = self._owners.get(name)
        if owner is None:
            super().__delattr__(name)
        else:
            delattr(owner, name)

    def __dir__(self):
        return sorted(set(super().__dir__()) | self._owners.keys())


def forward_module(name, owners):
    module = sys.modules[name]
    module._owners = owners
    module.__all__ = [key for key in owners if not key.startswith("_")]
    module.__class__ = _ForwardingModule
