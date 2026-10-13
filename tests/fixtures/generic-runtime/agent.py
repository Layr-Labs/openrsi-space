"""Exercise the real container boundary with synthetic model responses."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def post(url, body):
    request = Request(url, data=json.dumps(body).encode(),
                      headers={"Content-Type": "application/json", "Authorization": "Bearer testbed"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def main():
    task = json.loads(Path(os.environ["CATALYST_TASK"]).read_text())
    assert os.environ["OPENAI_API_KEY"] == "testbed"
    assert not any(os.environ.get(name) for name in (
        "TESTBED_OPENAI_API_KEY", "TESTBED_KIMI_CODE_API_KEY", "KIMI_CODE_API_KEY",
        "DUNGENESS_CHATGPT_AUTH_FILE", "DUNGENESS_CODEX_AUTH_FILE"))
    # A Docker internal network must expose no IPv4 default route.
    routes = Path("/proc/net/route").read_text().splitlines()[1:]
    assert not any(line.split()[1] == "00000000" for line in routes)
    try:
        connection = socket.create_connection(("1.1.1.1", 443), timeout=2)
    except OSError:
        pass
    else:
        connection.close()
        raise AssertionError("Harness unexpectedly has public internet access.")
    model = task["models"][0]
    endpoint = model["base_url"].rstrip("/") + "/chat/completions"
    try:
        post(endpoint, {"model": "not-declared", "messages": [{"role": "user", "content": "hello"}]})
    except HTTPError as error:
        assert error.code == 400
        assert json.load(error)["error"] == "model is not authorized for this run"
    else:
        raise AssertionError("Gateway accepted an undeclared model.")
    answer = post(endpoint, {"model": model["name"], "messages": [
        {"role": "user", "content": task["instruction"]}], "max_tokens": 5000})
    candidate = Path(task["workspace"]) / "candidate.json"
    candidate.write_text(answer["choices"][0]["message"]["content"])
    # This tiny fixture uses final independent verification in the outer worker.
    # The real ECDSA task additionally supplies evaluate --json during the run.
    # A leftover subprocess must not keep the job alive after entrypoint exit.
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(json.dumps({"runtime_checks": "passed", "claimed_score": 0}), flush=True)


if __name__ == "__main__":
    main()
