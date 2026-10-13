"""Immutable artifact objects. S3 credentials come from the SDK/IAM, never submissions."""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import shutil
import uuid

from .common import CatalystError, read_json


class ArtifactStorage:
    def __init__(self, root: Path, *, client=None):
        self.root = root
        path = root / "artifact-storage.json"
        self.config = read_json(path) if path.exists() else {"backend": "local"}
        if self.config.get("backend") not in {"local", "s3"}:
            raise CatalystError("Artifact storage backend must be local or s3.")
        self.client = client
        if self.config["backend"] == "s3":
            if not self.config.get("bucket") or not self.config.get("region"):
                raise CatalystError("S3 artifact storage requires bucket and region.")
            prefix = self.config.get("prefix", "catalyst")
            if not isinstance(prefix, str) or not prefix or any(
                part in {"", ".", ".."} for part in prefix.split("/")
            ):
                raise CatalystError("Invalid S3 artifact prefix.")
            if client is None:
                try:
                    import boto3
                    from botocore.config import Config
                except ImportError:
                    raise CatalystError("Install catalyst-research[s3] to enable S3 artifacts.") from None
                self.client = boto3.client(
                    "s3", region_name=self.config["region"],
                    config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
                )

    def local_path(self, sha256):
        if len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
            raise CatalystError("Invalid artifact digest.")
        return self.root / "artifact-objects" / f"{sha256}.zip"

    def put(self, path: Path):
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        size = path.stat().st_size
        local = self.local_path(digest)
        local.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not local.exists():
            temporary = local.with_suffix(f".{uuid.uuid4().hex}.tmp")
            shutil.copyfile(path, temporary)
            temporary.chmod(0o600)
            temporary.replace(local)
        descriptor = {"sha256": digest, "bytes": size, "media_type": "application/zip"}
        if self.config["backend"] == "local":
            return {**descriptor, "storage": {"backend": "local"}}
        key = f"{self.config.get('prefix', 'catalyst')}/sha256/{digest}.zip"
        # Content-addressed, conditional writes make retries and concurrent uploads safe.
        try:
            with local.open("rb") as stream:
                self.client.put_object(
                    Bucket=self.config["bucket"], Key=key, Body=stream,
                    ContentLength=size, ContentType="application/zip",
                    ServerSideEncryption="AES256", IfNoneMatch="*",
                    ChecksumSHA256=base64.b64encode(bytes.fromhex(digest)).decode(),
                    Metadata={"sha256": digest},
                )
        except Exception as error:
            response = getattr(error, "response", {})
            if response.get("ResponseMetadata", {}).get("HTTPStatusCode") != 412:
                raise CatalystError("Artifact upload failed; local evidence remains available.") from None
            head = self.client.head_object(Bucket=self.config["bucket"], Key=key)
            if head.get("ContentLength") != size or head.get("Metadata", {}).get("sha256") != digest:
                raise CatalystError("Existing S3 artifact does not match its content identity.")
        return {**descriptor, "storage": {
            "backend": "s3", "bucket": self.config["bucket"], "key": key,
            "region": self.config["region"],
        }}

    def download_url(self, descriptor):
        stored = descriptor["storage"]
        if stored["backend"] == "local":
            return None
        # Never sign a key/bucket selected by the requesting solver.
        if (self.config["backend"] != "s3" or stored["bucket"] != self.config["bucket"]
                or stored["region"] != self.config["region"]
                or stored["key"] != f"{self.config.get('prefix', 'catalyst')}/sha256/{descriptor['sha256']}.zip"):
            raise CatalystError("Artifact storage configuration does not match this object.")
        try:
            return self.client.generate_presigned_url(
                "get_object", Params={"Bucket": stored["bucket"], "Key": stored["key"],
                                     "ResponseContentDisposition": 'attachment; filename="artifact.zip"'},
                ExpiresIn=300,
            )
        except Exception:
            raise CatalystError("Artifact download signing is unavailable.") from None
