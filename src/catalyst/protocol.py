"""Public HTTP contract primitives shared by client and verifier."""
import uuid
from .common import CatalystError

YUKON_BINDING_PROTOCOL = "yukon-execution-binding-v1"

class APIError(CatalystError):
    def __init__(self, status, message, **details):
        super().__init__(message)
        self.status = status
        self.details = details

def identity(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise APIError(400, "Expected a canonical UUID.") from None
    return value
