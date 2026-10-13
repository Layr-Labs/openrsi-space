"""Owner downloads and explicit publication of immutable, sanitized run evidence."""
from __future__ import annotations

import base64
import hashlib
import html
import json
from pathlib import Path
import re
import tempfile
import zipfile

from .artifact_storage import ArtifactStorage
from .common import CatalystError, canonical, now, open_bundle, read_json, safe_relative, write_json

PROTOCOL = "catalyst-artifacts-v1"
KINDS = {"harness", "traces", "complete"}
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
SECRET_KEY = re.compile(
    r"(?i)^(?:authorization|proxy.authorization|cookie|set.cookie|"
    r"access_token|refresh_token|id_token|api_key|apikey|secret|password|"
    r"client_secret|OPENAI_API_KEY|YUKON_API_TOKEN|CATALYST_API_TOKEN)$"
)
SECRET_TEXT = re.compile(
    r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----.*?-----END (?:[A-Z ]+ )?PRIVATE KEY-----"
    r"|\b(?:ykn_[A-Za-z0-9_-]{20,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,}|"
    r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)"
    r"|(?i:\bBearer\s+[A-Za-z0-9._~+/-]+=*)",
    re.S,
)
ASSIGNMENT = re.compile(
    r'''(?i)((?:access_token|refresh_token|id_token|api_key|apikey|client_secret|password|'''
    r'''OPENAI_API_KEY|YUKON_API_TOKEN|CATALYST_API_TOKEN)["']?\s*[:=]\s*)'''
    r'''(?:"[^"\n]*"|'[^'\n]*'|[^\s,;}]+)'''
)
LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "GPL-3.0-only",
            "GPL-3.0-or-later", "AGPL-3.0-only", "MPL-2.0", "CC0-1.0", "CC-BY-4.0"}


def sanitized(data: bytes):
    text = data.decode("utf-8")  # Unknown binary trace material is never published.
    def redact(value):
        if isinstance(value, dict):
            return {key: "[REDACTED]" if SECRET_KEY.fullmatch(key) else redact(item)
                    for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        if isinstance(value, str):
            return ASSIGNMENT.sub(r'\1"[REDACTED]"', SECRET_TEXT.sub("[REDACTED]", value))
        return value
    try:
        original = json.loads(text)
        cleaned = redact(original)
        return data if cleaned == original else canonical(cleaned)
    except ValueError:
        pass
    lines = text.splitlines(keepends=True)
    try:
        if len(lines) > 1:
            values = [json.loads(line) for line in lines if line.strip()]
            cleaned = [redact(value) for value in values]
            if cleaned == values:
                return data
            return b"\n".join(canonical(value) for value in cleaned) + b"\n"
    except ValueError:
        pass
    return redact(text).encode()


def safe_read(path: Path, root: Path):
    relative = path.relative_to(root)
    if any(p.is_symlink() for p in [path, *path.parents] if p == root or root in p.parents):
        raise CatalystError("Artifact symlinks are not supported.")
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise CatalystError("Artifact file missing or exceeds the 64 MiB per-file limit.")
    safe_relative(relative.as_posix())
    return path.read_bytes()


def build_zip(path, files, identity):
    if len(files) > 10000 or sum(len(data) for data in files.values()) > MAX_TOTAL:
        raise CatalystError("Artifact export exceeds the 512 MiB / 10,000-file limit.")
    manifest = {
        "protocol": PROTOCOL, **identity,
        "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
                  for name, data in sorted(files.items())},
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted({**files, "artifact-manifest.json": canonical(manifest)}.items()):
            safe_relative(name)
            entry = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    path.chmod(0o600)


def collect_traces(store, job):
    folder = store.trace_path(job["id"]).parent
    files = {}
    missing = []
    allowed = (
        "build.json", "execution.log", "verifier-build.log", "verification.log",
        "failure.json", "usage.json", "verification.json", "harness-screening.json",
        "candidate-screening.json", "evaluation-history.json",
    )
    for name in allowed:
        path = folder / name
        if path.exists():
            files[name] = sanitized(safe_read(path, folder))
    for path in sorted((folder / "candidate").rglob("*")):
        if path.is_symlink():
            raise CatalystError("Candidate artifact contains a symlink.")
        if path.is_file():
            files[path.relative_to(folder).as_posix()] = sanitized(safe_read(path, folder))
    runtime = folder / "runtime.json"
    if runtime.exists():
        metadata = read_json(runtime)
        run = Path(metadata["record_path"]).parent
        config = ArtifactStorage(store.root).config
        roots = [Path(p).resolve() for p in config.get("run_roots", [str(store.root.parent / "worker")])]
        if not any(run.resolve().is_relative_to(root) for root in roots):
            raise CatalystError("Run artifacts are outside configured worker roots.")
        for name in ("record.json", "usage/summary.json", "usage/events.jsonl"):
            path = run / name
            if path.exists():
                files["dungeness/" + name] = sanitized(safe_read(path, run))
            else:
                missing.append("dungeness/" + name)
        outputs = sorted(run.glob("harbor/*/*/agent/harness-output.txt"))
        if not outputs:
            missing.append("dungeness/agent/harness-output.txt")
        for path in outputs:
            files["dungeness/" + path.relative_to(run).as_posix()] = sanitized(safe_read(path, run))
    else:
        missing.append("dungeness/runtime-not-created")
    # No internal request envelope, provider grants, auth homes, environment files,
    # images, dependency caches or arbitrary workspace files are exported.
    files["coverage.json"] = canonical({
        "missing": missing,
        "included": "Submitted source (separate bundle), final candidate, retained logs, "
                    "recorded Codex output, Dungeness record/events, usage and verification.",
        "excluded": ["credentials", "auth homes", "environment files", "container images",
                     "dependency caches", "unrecorded model internals"],
        "sanitization": "known-token-patterns-v1; recorded text may contain research code and data",
    })
    return files, missing


def seal(store, evaluation_id):
    """Idempotently package existing evidence. Never starts inference or verification."""
    from .remote import request_lock
    from .evaluator import APIError
    job = store.get(evaluation_id)
    if job["status"] not in {"completed", "failed", "cancelled"}:
        raise APIError(409, "Artifacts are available after the evaluation stops.")
    folder = store.trace_path(evaluation_id).parent
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with request_lock(folder / "artifact-export.lock"):
        target = folder / "artifact-export.json"
        storage = ArtifactStorage(store.root)
        if target.exists():
            exported = read_json(target)
            # Activating S3 migrates existing objects without rebuilding their bytes.
            changed = False
            for kind, descriptor in exported["artifacts"].items():
                if descriptor["storage"]["backend"] == "local" and storage.config["backend"] == "s3":
                    exported["artifacts"][kind] = storage.put(storage.local_path(descriptor["sha256"]))
                    changed = True
            if changed:
                write_json(target, exported)
            return exported
        archive = base64.b64decode(job["request"]["source"]["archive_base64"], validate=True)
        snapshot, _ = open_bundle(archive)
        if snapshot["version"] != job["request"]["source"]["digest"]:
            raise CatalystError("Stored harness identity does not match its request.")
        identity = {"evaluation_id": evaluation_id, "source_digest": snapshot["version"]}
        traces, missing = collect_traces(store, job)
        evaluation = job["request"]["evaluation"]
        # Grant references are service-private; the original source archive excludes evaluation.json.
        configuration = {key: value for key, value in evaluation.items() if key != "llm_access"}
        traces["evaluation.json"] = canonical(configuration)
        traces["result.json"] = sanitized(canonical(job["result"]))
        exported = {"protocol": PROTOCOL, **identity, "created_at": now(),
                    "missing": missing, "artifacts": {}}
        with tempfile.TemporaryDirectory(dir=folder, prefix="artifact-export-") as temporary:
            work = Path(temporary)
            (work / "harness.zip").write_bytes(archive)
            build_zip(work / "traces.zip", traces, {**identity, "kind": "traces"})
            build_zip(work / "complete.zip", {
                **traces, "harness.zip": archive,
                "problem-set.json": canonical(job["request"]["problem_set"]),
                "pricing.json": canonical(job["request"]["pricing"]),
                "verification-policy.json": canonical(job["request"]["judge"]),
            }, {**identity, "kind": "complete"})
            for kind in sorted(KINDS):
                exported["artifacts"][kind] = storage.put(work / f"{kind}.zip")
        write_json(target, exported)
        target.chmod(0o600)
        return exported


def sharing(store, evaluation_id):
    store.get(evaluation_id)
    with store.connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS artifact_publications (
            evaluation_id TEXT PRIMARY KEY, settings TEXT NOT NULL)""")
        row = db.execute("SELECT settings FROM artifact_publications WHERE evaluation_id=?",
                         (evaluation_id,)).fetchone()
    return json.loads(row["settings"]) if row else {"harness": False, "traces": False, "license": None}


def publish(store, evaluation_id, body):
    from .evaluator import APIError
    if (not isinstance(body, dict) or body.get("protocol") != PROTOCOL
            or set(body) - {"protocol", "harness", "traces", "license", "traces_reviewed"}
            or not ({"harness", "traces"} & body.keys())
            or any(type(body[k]) is not bool for k in ("harness", "traces") if k in body)):
        raise APIError(400, "Choose harness and/or traces publication explicitly.")
    if body.get("harness") is True and body.get("license") not in LICENSES:
        raise APIError(400, "Publishing a harness requires a supported explicit source license.")
    if body.get("traces") is True and body.get("traces_reviewed") is not True:
        raise APIError(400, "Review the sanitized trace download before making it public.")
    if body.get("harness") or body.get("traces"):
        exported = seal(store, evaluation_id)
        # Reject, rather than rewrite, secrets in the exact evaluated harness.
        if body.get("harness"):
            archive = base64.b64decode(store.get(evaluation_id)["request"]["source"]["archive_base64"])
            _, files = open_bundle(archive)
            from .cheat_filter import screen
            if screen(files, "harness")["status"] != "passed":
                raise APIError(409, "Harness source failed publication screening.")
            for data in files.values():
                try:
                    if sanitized(data) != data:
                        raise APIError(409, "Harness source contains possible credentials; cannot publish exact bytes.")
                except UnicodeDecodeError:
                    pass  # Original non-text knowledge files retain their exact identity.
    sharing(store, evaluation_id)  # Initialize the schema before the write transaction.
    with store.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT settings FROM artifact_publications WHERE evaluation_id=?",
                         (evaluation_id,)).fetchone()
        settings = json.loads(row["settings"]) if row else {"harness": False, "traces": False, "license": None}
        for kind in ("harness", "traces"):
            if kind in body:
                settings[kind] = body[kind]
        if body.get("harness"):
            if settings["license"] and settings["license"] != body["license"]:
                raise APIError(409, "An existing publication license cannot be replaced.")
            settings["license"] = body["license"]
        settings["updated_at"] = now()
        db.execute("INSERT OR REPLACE INTO artifact_publications VALUES (?,?)",
                   (evaluation_id, canonical(settings).decode()))
    return {"protocol": PROTOCOL, "evaluation_id": evaluation_id, **settings}


def manifest(store, evaluation_id, *, public=False):
    from .evaluator import APIError
    visibility = sharing(store, evaluation_id)
    if public and not (visibility["harness"] or visibility["traces"]):
        raise APIError(404, "Published artifacts not found.")
    exported = seal(store, evaluation_id)
    scope = "/public" if public else ""
    return {**{k: v for k, v in exported.items() if k != "artifacts"},
            "sharing": visibility,
            "artifacts": {
                kind: {k: v for k, v in item.items() if k != "storage"} | {
                    "download": f"{scope}/evaluations/{evaluation_id}/artifacts/{kind}",
                }
                for kind, item in exported["artifacts"].items()
                if not public or visibility.get(kind) is True
            }}


def download(store, evaluation_id, kind, *, public=False):
    from .evaluator import APIError
    if kind not in KINDS or (public and (kind == "complete" or not sharing(store, evaluation_id).get(kind))):
        raise APIError(404, "Artifact not found.")
    exported = seal(store, evaluation_id)
    item = exported["artifacts"][kind]
    storage = ArtifactStorage(store.root)
    return item, storage.download_url(item), storage.local_path(item["sha256"])


def public_page(store, evaluation_id):
    data = manifest(store, evaluation_id, public=True)
    links = []
    for kind, item in data["artifacts"].items():
        label = "Evaluated harness source" if kind == "harness" else "Sanitized recorded traces"
        license_note = (f"<p>Source license: {html.escape(data['sharing']['license'])}. "
                        "Bundled third-party licenses and notices still apply.</p>" if kind == "harness" else "")
        links.append(
            f"<article><h2>{label}</h2>{license_note}"
            f"<p><a href=\"{html.escape(item['download'])}/content\">Download ZIP</a>"
            f" · {item['bytes']:,} bytes</p><p>SHA-256: <code>{item['sha256']}</code></p></article>"
        )
    return (
        "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Shared Catalyst artifacts</title>"
        "<style>body{font:16px system-ui;max-width:850px;margin:48px auto;padding:0 24px;"
        "line-height:1.6;color:#172326}article{border-top:1px solid #ddd;margin-top:28px}"
        "code{overflow-wrap:anywhere}a{color:#006b60}h1,h2{line-height:1.25}</style>"
        "<h1>Shared Catalyst artifacts</h1>"
        f"<p>Evaluation <code>{html.escape(evaluation_id)}</code></p>"
        "<p>These files were explicitly published by the evaluation owner. "
        "Downloads contain untrusted research source and recorded output.</p>"
        + "".join(links)
        + f"<p><a href=\"/public/evaluations/{evaluation_id}/artifacts\">JSON manifest</a></p></html>"
    ).encode()
