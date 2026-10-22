"""Consume Dungeness's public file contract without importing runtime internals."""
from __future__ import annotations

import json
from pathlib import Path

from catalyst.common import CatalystError


def require_capabilities(root: Path, *required: str) -> None:
    """Check an operator-selected pinned runtime, never a submitted harness."""
    path = root / "runtime-contract.json"
    try:
        raw = path.read_text()
    except FileNotFoundError:
        # Only absence permits compatibility with older pins. An invalid or
        # incomplete declaration must never fall back to source-text detection.
        if path.is_symlink():
            raise CatalystError("Invalid Dungeness runtime-contract.json: dangling symlink.")
        from catalyst.integrations.dungeness.legacy import supports
        missing = [name for name in required if not supports(root, name)]
    except (OSError, UnicodeError) as error:
        raise CatalystError("Cannot read Dungeness runtime-contract.json.") from error
    else:
        try:
            document = json.loads(raw)
        except ValueError as error:
            raise CatalystError("Invalid Dungeness runtime-contract.json: expected JSON.") from error
        if (not isinstance(document, dict)
                or type(document.get("schema_version")) is not int
                or document["schema_version"] != 1
                or document.get("runtime") != "dungeness"):
            raise CatalystError("Unsupported Dungeness runtime contract; update Catalyst or repin the runtime.")
        capabilities = document.get("capabilities")
        if (not isinstance(capabilities, list)
                or any(not isinstance(name, str) or not name for name in capabilities)
                or len(set(capabilities)) != len(capabilities)):
            raise CatalystError("Invalid Dungeness runtime capabilities.")
        missing = sorted(set(required) - set(capabilities))
    if missing:
        raise CatalystError(
            "Dungeness lacks required native capabilities: " + ", ".join(missing) +
            ". Install a compatible clean runtime and repin it."
        )
