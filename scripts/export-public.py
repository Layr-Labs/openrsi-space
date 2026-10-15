#!/usr/bin/env python3
"""Export a reviewed public source tree without Git history or private state."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {
    ".gitattributes", ".gitignore", "README.md", "LICENSE", "LICENSE.md",
    "benchmark.json", "catalyst", "pyproject.toml", "uv.lock",
}
PUBLIC_MODULES = {
    "__init__", "catalog", "cli", "common", "credentials", "demo", "executable",
    "job_control", "problems", "progress", "protocol", "receipts", "remote", "server",
    "templates", "tiers", "yukon", "yukon_submit",
}
PUBLIC_FOLDERS = {"docs", "harnesses", "submission", "tests"}


def allowed(path):
    parts = path.parts
    name = path.as_posix()
    if name in ROOT_FILES or name in {
        ".github/workflows/benchmark.yml",
        "scripts/export-public.py",
    }:
        return True
    if any(part.startswith(".") for part in parts):
        return False
    if parts[0] in PUBLIC_FOLDERS:
        return path.suffix in {".md", ".py", ".json", ".html", ".png", ".pdf", ".patch"} or path.name == "Dockerfile"
    if parts[:2] == ("src", "catalyst"):
        if len(parts) == 3:
            return path.suffix == ".py" and path.stem in PUBLIC_MODULES
        return (
            len(parts) == 4 and (
                (parts[2] == "static" and path.name in {"app.js", "index.html", "style.css"})
                or (parts[2] == "problem-set" and path.name in {"initial.json", "pricing.json", "ecdsa.fail.md"})
                or (parts[2] == "runtime" and path.name in {"launch.py", "problem_server.py"})
            )
        )
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("Output must not already exist; never overwrite a reviewed export.")
    paths = set(subprocess.check_output(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT,
    ).decode().split("\0")) - {""}
    inventory = {}
    for name in sorted(paths):
        relative = Path(name)
        source = ROOT / relative
        if not source.exists():
            continue
        if not allowed(relative):
            raise SystemExit(f"Review unexpected public source path before export: {name}")
        if source.is_symlink() or not source.is_file():
            raise SystemExit(f"Only regular source files may be exported: {name}")
        inventory[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    output.mkdir(parents=True)
    for name in inventory:
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)
    (output / "PUBLIC_SOURCE.json").write_text(json.dumps({
        "schema_version": 1,
        "note": "Public working-tree snapshot; no Git history or verifier source.",
        "files": inventory,
    }, indent=2) + "\n")
    print(json.dumps({"directory": str(output), "files": len(inventory)}, indent=2))


if __name__ == "__main__":
    main()
