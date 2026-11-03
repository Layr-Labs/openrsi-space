"""Read provider availability through the selected runtime's public CLI."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from catalyst.common import CatalystError


def model_providers(root: Path) -> frozenset[str]:
    root = root.resolve()
    try:
        # No credentials, host Python import overrides, Docker, or network access
        # are needed to describe the operator-selected runtime.
        result = subprocess.run(
            [sys.executable, "-B", str(root / "dungeness"), "providers"],
            cwd=root, env={key: value for key, value in os.environ.items()
                           if key in {"PATH", "SYSTEMROOT"}},
            capture_output=True, text=True, timeout=15, check=True,
        )
        document = json.loads(result.stdout)
        providers = document["providers"]
        if (type(document.get("schema_version")) is not int
                or document["schema_version"] != 1 or document.get("runtime") != "dungeness"
                or not isinstance(providers, list) or not providers
                or any(not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", name)
                       for name in providers)
                or len(set(providers)) != len(providers)):
            raise ValueError
        return frozenset(providers)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        raise CatalystError(
            "Cannot read Dungeness provider registry. Select a clean runtime supporting "
            "`dungeness providers` (model-provider-registry-v1) and repin it."
        ) from None


def require_model_providers(root: Path, models) -> None:
    available = model_providers(root)
    if any(model["provider"] not in available for model in models):
        raise CatalystError("Provider is not supported by the selected Dungeness runtime. "
                            "Available providers: " + ", ".join(sorted(available)) + ".")
