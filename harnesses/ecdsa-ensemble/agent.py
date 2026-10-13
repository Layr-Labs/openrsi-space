"""Small non-Codex example: two processes, separate candidates, one run budget."""
from concurrent.futures import ProcessPoolExecutor
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile
import urllib.request


def decode_candidate(text):
    if text.startswith("```"):
        text = "\n".join(text.strip().splitlines()[1:-1])
    files = json.loads(text)["files"]
    if not isinstance(files, dict) or not files or len(files) > 200:
        raise ValueError("expected a bounded files mapping")
    total = 0
    for name, content in files.items():
        path = PurePosixPath(name)
        if (path.is_absolute() or ".." in path.parts or "\\" in name
                or path.suffix != ".rs" or not isinstance(content, str)):
            raise ValueError("expected relative Rust module files")
        total += len(content.encode())
    if total > 1024 * 1024 or "mod.rs" not in files:
        raise ValueError("candidate must include mod.rs and fit in 1 MiB")
    return files


def evaluate(path):
    result = subprocess.run(["evaluate", "--json", str(path)],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def propose(model, prompt, folder):
    if model["provider"] != "openai":
        raise ValueError("This example uses the OpenAI Responses API.")
    body = {"model": model["name"], "input": prompt, "max_output_tokens": 12000}
    request = urllib.request.Request(
        model["base_url"].rstrip("/") + "/responses", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer testbed"})
    with urllib.request.urlopen(request, timeout=600) as response:
        reply = json.loads(response.read(2 * 1024 * 1024))
    text = "".join(part.get("text", "") for item in reply.get("output", [])
                   for part in item.get("content", []) if part.get("type") == "output_text")
    files = decode_candidate(text)
    target = Path(folder)
    target.mkdir()
    for name, content in files.items():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return evaluate(target)


def run():
    task = json.loads(Path(os.environ["CATALYST_TASK"]).read_text())
    candidate = Path(task["workspace"]) / task["candidate_paths"][0]
    files = {p.relative_to(candidate).as_posix(): p.read_text() for p in candidate.rglob("*.rs")}
    baseline = evaluate(candidate)
    best = baseline["score"] if baseline["status"] == "ok" else float("inf")
    prompt = (task["instruction"] + "\nImprove this Rust module. Return only a JSON object with "
              "a files mapping containing ALL module files, including mod.rs. No prose.\n"
              + json.dumps(files))
    with tempfile.TemporaryDirectory(dir=task["workspace"], prefix=".ensemble-") as temporary:
        with ProcessPoolExecutor(max_workers=2) as pool:
            jobs = [(Path(temporary) / f"worker-{i}",
                     pool.submit(propose, model, prompt, str(Path(temporary) / f"worker-{i}")))
                    for i, model in enumerate(task["models"][:2])]
            for folder, job in jobs:
                try:
                    result = job.result()
                except Exception as error:
                    print(json.dumps({"worker": folder.name, "error": type(error).__name__}), flush=True)
                    continue
                if result["status"] == "ok" and result["score"] < best:
                    best = result["score"]
                    shutil.rmtree(candidate)
                    shutil.copytree(folder, candidate)


if __name__ == "__main__":
    run()
