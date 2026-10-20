"""Run stock Grok using only the assigned instructions and model gateway."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
from gateway_adapter import compatible_gateway

# Public Grok CLI OAuth client. The stored credential is the gateway placeholder,
# minted here so the airgapped run does not contact accounts.x.ai.
GROK_CLIENT = "https://auth.x.ai::b1a00492-073a-47ea-816f-4c329264a828"


def write_placeholder_login(home: Path) -> None:
    now = datetime.now(timezone.utc)
    home.mkdir(parents=True, exist_ok=True)
    document = {
        GROK_CLIENT: {
            "key": "testbed",
            "auth_mode": "external",
            "create_time": now.isoformat().replace("+00:00", "Z"),
            "user_id": "",
            "email": None,
            "coding_data_retention_opt_out": True,
            "expires_at": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        }
    }
    (home / "auth.json").write_text(json.dumps(document))


def main():
    task = json.loads(Path(os.environ["CATALYST_TASK"]).read_text())
    if task.get("gateway_auth") != "placeholder":
        raise SystemExit("This harness requires gateway-owned provider credentials.")
    harness = Path(__file__).resolve().parent
    home = Path("/tmp/stock-grok-home")
    write_placeholder_login(home)
    # The CLI selects its own Grok 4.7 client. The gateway meters task["model"].
    cli_model = "grok-4.7" if str(task["model"]).endswith("grok-4.7") else task["model"]
    command = [
        "grok",
        "-p", task["instruction"],
        "-m", cli_model,
        "--disable-web-search",
        "--permission-mode", "bypassPermissions",
        "--always-approve",
        "--no-alt-screen",
    ]
    with compatible_gateway(task["gateway"], task["model"], cli_model) as local_url:
        env = {**os.environ,
               "GROK_HOME": str(home),
               "XAI_API_KEY": "testbed",
               "GROK_MODELS_BASE_URL": local_url,
               "GROK_CLI_CHAT_PROXY_BASE_URL": local_url,
               "GROK_AUTH_PROVIDER_COMMAND": f"python3 {harness / 'mint_auth.py'}",
               "GROK_AUTH_TOKEN_TTL": "3600"}
        result = subprocess.run(command, cwd=task["workspace"], env=env)
    # The trusted worker independently checks usage and the retained candidate,
    # including when the gateway stops model requests at the spending limit.
    print(json.dumps({"event": "grok_finished", "exit_code": result.returncode}), flush=True)


if __name__ == "__main__":
    main()
