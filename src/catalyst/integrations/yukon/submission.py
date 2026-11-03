"""Stock Yukon submission followed by a credential-free persistent job binding."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from catalyst.common import CatalystError, read_json, write_json
from catalyst.protocol import identity
from catalyst.integrations.yukon.receipts import RECEIPT_PATH, check_receipt, read_receipt
from catalyst.client.transport import endpoint, fetch, solver_token
from catalyst.client.state import request_lock
from catalyst.protocol import YUKON_BINDING_PROTOCOL as PROTOCOL

LEGACY_BENCHMARKS = {"layr-labs/catalyst", "8d3a2daa-afab-4685-b93a-7443c83049d2"}


def local_benchmark(root):
    for key in ('yukon.benchmark-id', 'hilbert.benchmark-id'):
        result = subprocess.run(['git', 'config', '--get', key], cwd=root,
                                capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    return None


def require_current_board(benchmark):
    if benchmark in LEGACY_BENCHMARKS:
        raise CatalystError(
            'This checkout or pending publication targets the historical layr-labs/catalyst board. '
            'Keep its receipt, note and pending record unchanged. Clone the current board into a new directory '
            'with yukon clone bxue-l2/openrsi-space, copy the existing verification.json to submission/verification.json, '
            'and publish from there using the same solver account. No new local or paid remote run is needed.')


def bind_job(root, job_id, benchmark_id, *, reference=None):
    key = solver_token()
    if not key.startswith("ykn_"):
        raise CatalystError("Execution binding requires your Yukon API key, not a OpenRSI session token.")
    reference = reference if reference is not None else read_receipt(root / RECEIPT_PATH)
    body = {"protocol": PROTOCOL, "job_id": identity(job_id),
            "benchmark_id": identity(benchmark_id), "reference": reference}
    result = json.loads(fetch(endpoint() + "/verifications/yukon-bind", key, document=body))
    if (not isinstance(result, dict) or result.get("protocol") != PROTOCOL
            or result.get("job_id") != job_id or result.get("benchmark_id") != benchmark_id
            or result.get("evaluation_id") != reference["evaluation_id"]):
        raise CatalystError("The service returned a mismatched execution binding.")
    for field in ("execution_id", "submission_id"):
        identity(result.get(field))
    return result


def submit(root: Path, *, note_file, model, harness, dependencies_file=None,
           no_dependencies=False, benchmark=None):
    root = root.resolve()
    manifest = read_json(root / "benchmark.json")
    if manifest.get("editablePaths") != [RECEIPT_PATH.as_posix()]:
        raise CatalystError("This helper requires a receipt-only benchmark checkout.")
    selected_benchmark = benchmark or local_benchmark(root)
    require_current_board(selected_benchmark)
    pending = root / ".catalyst/yukon/pending-submission.json"
    pending.parent.mkdir(parents=True, exist_ok=True)
    with request_lock(pending):
        if pending.exists():
            saved = read_json(pending)
            require_current_board(saved.get("benchmark_id"))
            if saved.get("phase") != "binding":
                raise CatalystError(
                    "The previous Yukon submission outcome is unknown. Inspect yukon submissions "
                    "before retrying; use openrsi-space yukon-bind for an existing job.")
            if (saved["endpoint"] != endpoint()
                    or saved["reference"] != read_receipt(root / RECEIPT_PATH)):
                raise CatalystError("Restore the pending submission's endpoint and receipt before resuming.")
        else:
            if bool(dependencies_file) == bool(no_dependencies):
                raise CatalystError("Declare --no-dependencies or provide --dependencies-file.")
            if not Path(note_file).is_file():
                raise CatalystError("Submission note file does not exist.")
            check_receipt(root)
            saved = {"phase": "submitting", "endpoint": endpoint(),
                     "reference": read_receipt(root / RECEIPT_PATH)}
            write_json(pending, saved)
            pending.chmod(0o600)
            command = ["yukon", "submit", *([benchmark] if benchmark else []),
                       "--note-file", str(Path(note_file).resolve()), "--model", model,
                       "--harness", harness, "--json"]
            command += (["--dependencies-file", str(Path(dependencies_file).resolve())]
                        if dependencies_file else ["--no-dependencies"])
            # Inherit the solver's normal login; no credential is passed in argv or saved.
            result = subprocess.run(command, cwd=root, stdout=subprocess.PIPE, text=True)
            if result.returncode:
                raise CatalystError(
                    "Yukon submit failed; its outcome may be uncertain. Inspect yukon submissions "
                    "before retrying. The pending record prevents a duplicate submission.")
            try:
                response = json.loads(result.stdout)
                job, submission = response["job"], response["submission"]
                job_id = identity(job["id"])
                benchmark_id = identity(submission["benchmarkId"])
                submission_id = identity(submission["id"])
                if job["submissionId"] != submission_id or job["benchmarkId"] != benchmark_id:
                    raise ValueError
            except (ValueError, KeyError, TypeError):
                raise CatalystError(
                    "Yukon returned an unrecognized submission response. Inspect yukon submissions "
                    "and bind its existing job; do not repeat the upload.") from None
            saved.update(phase="binding", job_id=job_id,
                         benchmark_id=benchmark_id, submission_id=submission_id)
            write_json(pending, saved)
            pending.chmod(0o600)
        require_current_board(saved["benchmark_id"])
        # Names are resolved by Yukon; compare UUID destinations when the local
        # checkout supplies one. Retain any created job so retry cannot upload twice.
        try:
            selected_id = identity(selected_benchmark)
        except (CatalystError, ValueError, TypeError):
            selected_id = None
        if selected_id and selected_id != saved["benchmark_id"]:
            raise CatalystError('Yukon returned a different benchmark than this checkout requested. '
                                'The job is retained in the pending record; do not repeat the upload.')
        result = bind_job(root, saved["job_id"], saved["benchmark_id"], reference=saved["reference"])
        if result["submission_id"] != saved["submission_id"]:
            raise CatalystError("The service bound a different Yukon submission.")
        write_json(root / f".catalyst/yukon/submissions/{saved['job_id']}.json", result)
        pending.unlink()
        return result
