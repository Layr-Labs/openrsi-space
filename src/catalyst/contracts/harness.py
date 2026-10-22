"""Executable harness schema shared by clients and verifiers."""
import re
from catalyst.common import CatalystError, safe_relative

INTERFACE = "catalyst-exec-v1"
IMAGE_RE = re.compile(r"sha256:[0-9a-f]{64}")

def validate_execution(execution: dict) -> None:
    if not isinstance(execution, dict) or execution.get("interface") != INTERFACE:
        raise CatalystError(f"Executable harnesses require interface {INTERFACE}.")
    if set(execution) != {"interface", "dockerfile", "entrypoint"}:
        raise CatalystError("execution requires only interface, dockerfile, and entrypoint.")
    if not isinstance(execution["dockerfile"], str):
        raise CatalystError("dockerfile must be a relative filename.")
    safe_relative(execution["dockerfile"])
    argv = execution["entrypoint"]
    if (not isinstance(argv, list) or not argv or len(argv) > 64
            or any(not isinstance(item, str) or not item or "\0" in item for item in argv)):
        raise CatalystError("entrypoint must be a nonempty command argument list.")

# Runtime policy and result references are not executable build inputs.
SOURCE_EXCLUDES = frozenset({"evaluation.json", "verification.json"})
