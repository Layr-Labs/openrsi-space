"""Run public tests and check a fresh wheel without stale local build output."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=ROOT, env=None, stdout=None):
    subprocess.run(args, cwd=cwd, env=env, stdout=stdout, check=True)


def main():
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join(
        str(ROOT / path) for path in ("src", "tests"))}
    run(sys.executable, "-m", "unittest", "discover", "-s", "tests", env=environment)
    with tempfile.TemporaryDirectory(prefix="openrsi-check-") as temporary:
        work = Path(temporary)
        source = work / "source"
        source.mkdir()
        for name in ("pyproject.toml", "README.md"):
            shutil.copy2(ROOT / name, source / name)
        shutil.copytree(ROOT / "src", source / "src", ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", "*.pyo", "*.egg-info"))
        package = source / "src/openrsi_space"
        hashes = {str(path.relative_to(package)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in package.rglob("*") if path.is_file()}
        manifest = work / "package-hashes.json"
        manifest.write_text(json.dumps(hashes))
        run("uv", "build", "--wheel", "--out-dir", str(work / "dist"), cwd=source)
        wheels = list((work / "dist").glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("Expected exactly one built wheel")
        requirements = work / "requirements.txt"
        run("uv", "export", "--locked", "--no-emit-project", "--output-file", str(requirements), stdout=subprocess.DEVNULL)
        virtualenv = work / "venv"
        run("uv", "venv", "--python", sys.executable, str(virtualenv))
        python = virtualenv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run("uv", "pip", "install", "--python", str(python), "-r", str(requirements), str(wheels[0]))
        # -I excludes both PYTHONPATH and the check script's directory.
        run(str(python), "-I", str(ROOT / "script/check_installed.py"), str(manifest), cwd=work)
    print("Public tests and installed-wheel checks passed.", flush=True)


if __name__ == "__main__":
    main()
