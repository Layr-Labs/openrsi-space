"""Temporary provider access for Dungeness; native Codex helpers remain compatible.

Dungeness remains the sole source of model usage and budget enforcement.
Only access credentials cross HTTPS; renewable credentials stay on the client.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from .common import CatalystError, canonical
from .model_access import validate_token

PROVIDERS = {"openai-chatgpt", "openai", "anthropic", "openrouter", "moonshot", "kimi-code"}
PREFIX = "chatgpt_"
ACCESS_PREFIX = "providers_"
PROVIDER_ENV = {"openai": "TESTBED_OPENAI_API_KEY", "anthropic": "TESTBED_ANTHROPIC_API_KEY",
                "openrouter": "TESTBED_OPENROUTER_API_KEY", "moonshot": "TESTBED_MOONSHOT_API_KEY",
                "kimi-code": "TESTBED_KIMI_CODE_API_KEY"}


def validate_access(access):
    if (not isinstance(access, dict) or set(access) != {"access_token", "id_token", "account_id", "last_refresh"}
            or any(not isinstance(v, str) or not v or len(v) > 8192 for v in access.values())):
        raise CatalystError("A valid ChatGPT Codex login is required.")


def encode_codex_access(path):
    try:
        document = json.loads(Path(path).expanduser().read_text())
        if document.get("auth_mode") != "chatgpt":
            raise ValueError
        access = {name: document["tokens"].get(name) for name in ("access_token", "id_token", "account_id")}
        # Codex recognizes the login without this metadata but omits bearer
        # authentication on Responses requests. Preserve the native timestamp.
        access["last_refresh"] = document.get("last_refresh")
        validate_access(access)
        result = PREFIX + base64.urlsafe_b64encode(canonical(access)).decode()
        validate_token(result)
        return result
    except (OSError, ValueError, KeyError, TypeError):
        raise CatalystError("Cannot read a valid ChatGPT login from the selected Codex auth file.") from None


def decode_codex_access(value):
    try:
        if not isinstance(value, str) or not value.startswith(PREFIX):
            raise ValueError
        access = json.loads(base64.b64decode(value[len(PREFIX):], altchars=b"-_", validate=True))
        validate_access(access)
        return access
    except (ValueError, TypeError):
        raise CatalystError("Invalid temporary Codex access; submit using --codex-auth-file.") from None


class CodexAccess:
    def __init__(self, evaluation, credential):
        if evaluation["model"]["provider"] != "openai-chatgpt":
            raise CatalystError("This worker supports the native Dungeness ChatGPT provider.")
        self.access = decode_codex_access(credential)
        self.directory = None

    def __enter__(self):
        if subprocess.check_output(["stat", "-f", "-c", "%T", "/dev/shm"], text=True).strip() != "tmpfs":
            raise CatalystError("Temporary provider access requires Linux tmpfs.")
        self.directory = Path(tempfile.mkdtemp(prefix="catalyst-codex-", dir="/dev/shm"))
        self.directory.chmod(0o700)
        try:
            self.auth_file = self.directory / "auth.json"
            self.auth_file.write_bytes(canonical({
                "auth_mode": "chatgpt", "OPENAI_API_KEY": None,
                "last_refresh": self.access["last_refresh"],
                "tokens": {**{k: self.access[k] for k in ("access_token", "id_token", "account_id")},
                           "refresh_token": "refresh-disabled-on-remote-worker"}}))
            self.auth_file.chmod(0o600)
            self.env_file = self.directory / "runtime.env"
            self.env_file.touch(mode=0o600)
            return self
        except BaseException:
            self.__exit__()
            raise

    def scrub(self, root):
        secrets = [self.access[k].encode() for k in ("access_token", "id_token")]
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink() and path.stat().st_size <= 16 * 1024 * 1024:
                data = path.read_bytes()
                cleaned = data
                for secret in secrets:
                    cleaned = cleaned.replace(secret, b"[REDACTED]")
                if cleaned != data:
                    path.write_bytes(cleaned)

    def __exit__(self, *_):
        if self.directory:
            shutil.rmtree(self.directory)
        self.access.clear()


def encode_provider_access(document):
    """Encode a private provider map for the existing HTTPS handoff channel."""
    validate_provider_access(document)
    encoded = ACCESS_PREFIX + base64.urlsafe_b64encode(canonical(document)).decode()
    validate_token(encoded)
    return encoded


def validate_provider_access(document):
    if not isinstance(document, dict) or not document or set(document) - PROVIDERS:
        raise CatalystError("Provider access must map supported providers to temporary credentials.")
    for provider, value in document.items():
        if provider == "openai-chatgpt":
            validate_access(value)
        else:
            validate_token(value)
            if any(c in value for c in "'\"\\$`#"):
                raise CatalystError("Provider token contains unsupported environment-file characters.")


class ProviderAccess:
    """Stage credentials in Linux tmpfs, never in a run or submitted image."""
    def __init__(self, evaluation, credential):
        from .tiers import evaluation_models
        providers = {m["provider"] for m in evaluation_models(evaluation)}
        try:
            if credential.startswith(PREFIX):
                self.access = {"openai-chatgpt": decode_codex_access(credential)}
            elif credential.startswith(ACCESS_PREFIX):
                self.access = json.loads(base64.b64decode(
                    credential[len(ACCESS_PREFIX):], altchars=b"-_", validate=True))
            elif len(providers) == 1 and "openai-chatgpt" not in providers:
                self.access = {next(iter(providers)): credential}
            else:
                raise ValueError
            validate_provider_access(self.access)
            if set(self.access) != providers:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise CatalystError("Temporary access must cover exactly the run's provider set.") from None
        self.directory = None
        self.auth_file = None

    def __enter__(self):
        if subprocess.check_output(["stat", "-f", "-c", "%T", "/dev/shm"], text=True).strip() != "tmpfs":
            raise CatalystError("Temporary provider access requires Linux tmpfs.")
        self.directory = Path(tempfile.mkdtemp(prefix="catalyst-provider-", dir="/dev/shm"))
        self.directory.chmod(0o700)
        try:
            self.env_file = self.directory / "runtime.env"
            self.env_file.touch(mode=0o600)
            self.env_file.write_text("".join(
                f"{PROVIDER_ENV[p]}={value}\n" for p, value in self.access.items()
                if p in PROVIDER_ENV))
            if "openai-chatgpt" in self.access:
                self.auth_file = self.directory / "auth.json"
                self.auth_file.touch(mode=0o600)
                self.auth_file.write_bytes(canonical({"tokens": self.access["openai-chatgpt"]}))
            return self
        except BaseException:
            self.__exit__()
            raise

    def scrub(self, root):
        secrets = []
        for provider, value in self.access.items():
            secrets.extend([value["access_token"], value["id_token"]]
                           if provider == "openai-chatgpt" else [value])
        for path in root.rglob("*"):
            if path.is_file() and not path.is_symlink() and path.stat().st_size <= 16 * 1024 * 1024:
                data = path.read_bytes()
                cleaned = data
                for secret in secrets:
                    cleaned = cleaned.replace(secret.encode(), b"[REDACTED]")
                if cleaned != data:
                    path.write_bytes(cleaned)

    def __exit__(self, *_):
        if self.directory:
            shutil.rmtree(self.directory)
        self.access.clear()
