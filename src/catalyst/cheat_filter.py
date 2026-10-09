"""Conservative deterministic screening; not a proof that arbitrary code is safe."""
from __future__ import annotations

import re
from pathlib import Path

POLICY = "catalyst-screen-v1"
# Report rule/location, never matched source: a match may itself be a credential.
COMMON = {
    "embedded-private-key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "embedded-api-key": r"\b(?:ykn_[a-f0-9]{40,}|sk-(?:proj-)?[A-Za-z0-9_-]{32,})\b",
    "host-container-control": r"(?:/var/run/docker\.sock|/run/containerd/containerd\.sock)",
    "cloud-metadata-access": r"(?:169\.254\.169\.254|metadata\.google\.internal)",
}
CANDIDATE = {
    "filesystem-access": r"\b(?:std|alloc)\s*::\s*fs\b|\b(?:File|OpenOptions)\s*::",
    "process-or-network-access": r"\b(?:std\s*::\s*(?:process|net)|Command\s*::|TcpStream\s*::|UdpSocket\s*::)",
    "unsafe-or-ffi": r"\bunsafe\b|\bextern\s*(?:\"[^\"]*\"\s*)?\{|(?:global_asm|asm)\s*!",
    "external-source-inclusion": r"\binclude(?:_str|_bytes)?\s*!|#\s*\[\s*path\s*=",
    "verifier-internals": r"(?:/logs/verifier|/opt/evaluator|/tests/grade\.py|score\.json|eval_circuit)",
    "grouped-host-access": r"\b(?:fs|process|net)\s*(?:::|as\b|[,}])",
    "root-module-alias": r"\buse\s+(?:::)?\s*std\s*(?:as\b|;)|\bself\s+as\b|\bextern\s+crate\b",
}


def without_comments(text: str) -> str:
    """Blank Rust comments, retaining offsets, strings and nested block comments."""
    token = re.compile(
        r"""//[^\n]*|/\*|b?'(?:\\(?:x[0-9a-fA-F]{2}|u\{[0-9a-fA-F_]+\}|.)|[^'\\])'"""
        r'|r(?P<hashes>\#{0,255})".*?"(?P=hashes)|"(?:\\.|[^"\\])*"', re.S)
    result, cursor = [], 0
    while match := token.search(text, cursor):
        result.append(text[cursor:match.start()])
        end = match.end()
        if match.group().startswith("/*"):
            depth = 1
            while depth and end < len(text):
                nested = re.search(r"/\*|\*/", text[end:])
                if nested is None:
                    end = len(text)
                    break
                depth += 1 if nested.group() == "/*" else -1
                end += nested.end()
        if match.group().startswith(("//", "/*")):
            result.append("".join("\n" if char == "\n" else " " for char in text[match.start():end]))
        else:
            result.append(text[match.start():end])
        cursor = end
    return "".join(result) + text[cursor:]


def findings_for(files: dict[str, bytes], kind: str) -> list:
    """Static screening, not a proof of safety; never return matched source."""
    if kind not in {"harness", "candidate"}:
        raise ValueError("Unknown screening scope.")
    findings = []
    for name, data in sorted(files.items()):
        if kind == "candidate" and not name.endswith(".rs"):
            findings.append({"path": name, "rule": "candidate-not-rust", "line": 1})
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            if kind == "candidate":
                findings.append({"path": name, "rule": "candidate-not-utf8", "line": 1})
            continue
        code = without_comments(text).replace("r#", "  ") if kind == "candidate" else text
        rules = [(rule, pattern, text) for rule, pattern in COMMON.items()]
        if kind == "candidate":
            rules += [(rule, pattern, code) for rule, pattern in CANDIDATE.items()]
        for rule, pattern, source in rules:
            matched = re.search(pattern, source)
            if matched:
                findings.append({"path": name, "rule": rule, "line": text.count("\n", 0, matched.start()) + 1})
    return findings


def candidate_findings(root: Path) -> list:
    """Sidecar input has already been safely unpacked; bound the screening read."""
    files, total = {}, 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            return [{"path": path.relative_to(root).as_posix(), "rule": "non-regular-file", "line": 1}]
        if path.is_dir():
            continue
        with path.open("rb") as stream:
            data = stream.read(8 * 1024 * 1024 - total + 1)
        total += len(data)
        if total > 8 * 1024 * 1024 or len(files) >= 2000:
            return [{"path": ".", "rule": "candidate-size-limit", "line": 1}]
        files[path.relative_to(root).as_posix()] = data
    return findings_for(files, "candidate")


def screen(files: dict[str, bytes], kind: str) -> dict:
    """Bind the private report to exactly the bytes screened by the worker."""
    from .common import digest_files
    findings = findings_for(files, kind)
    return {"policy": POLICY, "scope": kind, "digest": digest_files(files),
            "status": "rejected" if findings else "passed", "findings": findings}


def require_pass(report: dict) -> None:
    from .common import CatalystError
    if report["status"] != "passed":
        raise CatalystError("Deterministic cheat screening rejected this package; inspect the private screening report.")


def install_sidecar_screen(runtime: Path) -> list[str]:
    """Gate every intermediate evaluation without changing scoring or capture."""
    from .common import CatalystError
    relative = "verifiers/ecdsa-fail/benchmark-sh"
    folder = runtime / relative
    serve = folder / "serve.py"
    anchor = 'if __name__ == "__main__":'
    if serve.read_text().count(anchor) != 1:
        raise CatalystError("Pinned ECDSA sidecar screening anchors changed.")
    # Dungeness copies only its known verifier filenames. Embed the pure policy
    # in serve.py rather than depending on an extra file the compiler drops.
    policy = Path(__file__).read_text().split("\ndef screen(", 1)[0]
    hook = (
        "\nimport types as _catalyst_types\n"
        "_catalyst_screen = _catalyst_types.ModuleType('catalyst_screen')\n"
        f"exec(compile({policy!r}, 'catalyst_screen.py', 'exec'), _catalyst_screen.__dict__)\n"
    ) + '''
_catalyst_original_grade = grade.score_candidate
def _catalyst_screened_grade(candidate, *args, **kwargs):
    findings = _catalyst_screen.candidate_findings(candidate)
    if findings:
        return {"status": "screen_rejected", "score": grade.INVALID_SCORE,
                "avg_toffoli": None, "peak_qubits": None}
    return _catalyst_original_grade(candidate, *args, **kwargs)
grade.score_candidate = _catalyst_screened_grade

'''
    serve.write_text(serve.read_text().replace(anchor, hook + anchor))
    return [f"{relative}/serve.py"]
