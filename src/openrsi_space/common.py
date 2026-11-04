from __future__ import annotations
from openrsi_space.compatibility import LEGACY_STATE, SNAPSHOT_FILENAME

from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import uuid
import zipfile

MAX_BUNDLE_BYTES = 64 * 1024 * 1024
KINDS = {"problem", "harness", "run"}
RESERVED = SNAPSHOT_FILENAME
IGNORED = {".git", ".openrsi", LEGACY_STATE, ".venv", "__pycache__", ".DS_Store", ".env"}


class OpenRSIError(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,79}", value):
        raise OpenRSIError("IDs must be 1–80 lowercase letters, digits, dots, underscores, or hyphens.")
    return value


def version_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise OpenRSIError("A version must be a complete SHA-256 hash.")
    return value


def finite_number(value, *, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise OpenRSIError("Expected a finite number.")
    if nonnegative and value < 0:
        raise OpenRSIError("Expected a nonnegative number.")
    return float(value)


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, document) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


def safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or ".." in path.parts or "\\" in value
            or value != path.as_posix() or path.as_posix() == "."):
        raise OpenRSIError(f"Unsafe relative path: {value!r}")
    return value


def validate_document(document: dict) -> None:
    if (isinstance(document, dict) and document.get("kind") in (None, "harness")
            and "execution" not in document
            and {"interface", "dockerfile", "entrypoint"} <= document.keys()):
        raise OpenRSIError(
            "This is an execution object, not a complete harness.json. Put it under "
            "execution and add schema_version: 1, kind: harness, id, and title. "
            "Generate a complete starter with: openrsi-space harness create my-agent "
            "--output ./my-agent. See docs/executable-harness.md."
        )
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise OpenRSIError("Expected a schema_version: 1 document.")
    kind = document.get("kind")
    if kind not in KINDS:
        raise OpenRSIError("Unknown document kind.")
    identifier(document.get("id"))
    if not isinstance(document.get("title"), str) or not document["title"].strip():
        raise OpenRSIError("A title is required.")
    if kind == "problem":
        if "release" in document or "slug" in document:
            for key in ("release", "slug"):
                value = document.get(key)
                if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
                    raise OpenRSIError("A versioned problem requires a safe slug and release tag.")
        metric = document.get("metric", {})
        if not isinstance(metric, dict) or not isinstance(metric.get("name"), str) or not metric["name"]:
            raise OpenRSIError("A problem requires a named metric.")
        if metric.get("direction") not in {"minimize", "maximize"}:
            raise OpenRSIError("Metric direction must be minimize or maximize.")
    if kind == "harness":
        if "execution" in document:
            from openrsi_space.contracts.harness import validate_execution
            validate_execution(document["execution"])
            if "agent" in document or "agent_options" in document:
                raise OpenRSIError("An executable harness cannot select a host agent or adapter.")
        elif not isinstance(document.get("agent"), str):
            raise OpenRSIError("A harness requires an executable contract or Dungeness agent reference.")
    if kind == "run":
        if document.get("evidence") not in {"contributor-reported", "demo"}:
            raise OpenRSIError("This prototype accepts contributor-reported or demo evidence.")
        for key, kind in (("problem", "problem"), ("harness", "harness")):
            ref = document.get(key, {})
            if not isinstance(ref, dict):
                raise OpenRSIError(f"Missing {key} reference.")
            identifier(ref.get("id"))
            version_id(ref.get("version"))
        metric = document.get("metric", {})
        if not isinstance(metric, dict) or metric.get("direction") not in {"minimize", "maximize"}:
            raise OpenRSIError("A run requires a metric direction.")
        for field in ("model", "conditions", "status"):
            if not isinstance(document.get(field), str) or not document[field]:
                raise OpenRSIError(f"A run requires a {field}.")
        observations = document.get("observations")
        if not isinstance(observations, list):
            raise OpenRSIError("A run requires a list of observations.")
        for point in observations:
            if not isinstance(point, dict) or not {"score", "cost"} <= point.keys():
                raise OpenRSIError("Each observation requires score and cost.")
            finite_number(point["score"])
            finite_number(point["cost"], nonnegative=True)
        if document.get("total_cost") is not None:
            finite_number(document["total_cost"], nonnegative=True)


def digest_files(files: dict[str, bytes]) -> str:
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())}
    return hashlib.sha256(canonical(hashes)).hexdigest()


def make_bundle(files: dict[str, bytes]) -> tuple[dict, bytes]:
    manifests = [name for name in ("problem.json", "harness.json", "run.json") if name in files]
    if len(manifests) != 1 or RESERVED in files:
        raise OpenRSIError("A bundle must contain exactly one problem, harness, or run manifest.")
    document = json.loads(files[manifests[0]])
    validate_document(document)
    if manifests[0] != f"{document['kind']}.json":
        raise OpenRSIError("Manifest filename and kind disagree.")
    if len(files) > 2000 or sum(map(len, files.values())) > MAX_BUNDLE_BYTES:
        raise OpenRSIError("Bundle exceeds the prototype's 64 MiB / 2000-file limit.")
    for name in files:
        safe_relative(name)
        if any(part in IGNORED or part.startswith(".env") for part in PurePosixPath(name).parts):
            raise OpenRSIError(f"Excluded file in bundle: {name}")
    snapshot = {
        "schema_version": 1, "kind": document["kind"], "id": document["id"],
        "version": digest_files(files), "document": document,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted({**files, RESERVED: canonical(snapshot)}.items()):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return snapshot, buffer.getvalue()


def open_bundle(content: bytes) -> tuple[dict, dict[str, bytes]]:
    if len(content) > MAX_BUNDLE_BYTES:
        raise OpenRSIError("Bundle exceeds 64 MiB.")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > 2001 or sum(e.file_size for e in entries) > MAX_BUNDLE_BYTES:
                raise OpenRSIError("Expanded bundle exceeds the allowed size.")
            if len({e.filename for e in entries}) != len(entries):
                raise OpenRSIError("Duplicate paths in bundle.")
            files = {}
            for entry in entries:
                safe_relative(entry.filename)
                if entry.is_dir() or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise OpenRSIError("Directory entries and symlinks are not supported.")
                files[entry.filename] = archive.read(entry)
        declared = json.loads(files.pop(RESERVED))
        actual, _ = make_bundle(files)
        if declared != actual:
            raise OpenRSIError("Bundle does not match its content hashes.")
        return actual, files
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as error:
        raise OpenRSIError(f"Invalid bundle: {error}") from error


def snapshot_directory(path: Path, *, exclude: frozenset[str] = frozenset(),
                       harness_document=None) -> tuple[dict, bytes]:
    from .source_snapshot import capture
    files = capture(path, exclude=exclude, harness=harness_document is not None)
    if harness_document is not None:
        if "harness.json" in files:
            raise OpenRSIError("Use the existing harness.json entrypoint or remove the launch override.")
        files["harness.json"] = canonical(harness_document)
    return make_bundle(files)


def extract_bundle(content: bytes, destination: Path) -> dict:
    snapshot, files = open_bundle(content)
    if destination.exists() and any(destination.iterdir()):
        raise OpenRSIError(f"Destination must be empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return snapshot
