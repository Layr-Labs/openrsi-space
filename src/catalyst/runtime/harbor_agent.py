"""One trusted Harbor adapter for all executable harnesses.

Copied into a disposable Dungeness checkout, never supplied by a solver.
"""
import json

from harbor.agents.installed.base import BaseInstalledAgent


class CatalystExecutable(BaseInstalledAgent):
    def __init__(self, *args, task_input, **kwargs):
        self.task_input = task_input
        for option in ("reasoning_effort", "reasoning_summary", "model_context_window", "web_search"):
            kwargs.pop(option, None)
        super().__init__(*args, **kwargs)

    @staticmethod
    def name():
        return "catalyst-executable"

    def get_version_command(self):
        return None

    def parse_version(self, stdout):
        return None

    async def install(self, environment):
        await self.exec_as_agent(
            environment, command="test -f /opt/catalyst/execution.json && command -v python3",
        )

    async def run(self, instruction, environment, context):
        provider = self.task_input.get("model_provider", "openai")
        provider = "chatgpt" if provider == "openai-chatgpt" else provider
        task = {**self.task_input, "instruction": instruction, "model": self.model_name,
                "workspace": "/workspace/repo", "gateway": f"http://gateway:8080/model/{provider}/v1"}
        file = self.logs_dir / "catalyst-task.json"
        file.write_text(json.dumps(task))
        await environment.upload_file(file, "/tmp/catalyst-task.json")
        result = await self.exec_as_agent(
            environment, command="python3 /opt/catalyst/launch.py /tmp/catalyst-task.json",
            cwd="/workspace/repo",
        )
        (self.logs_dir / "harness-output.txt").write_text(
            (result.stdout or "") + "\n" + (result.stderr or ""))

    def populate_context_post_run(self, context):
        # Dungeness's gateway, rather than submitted stdout, supplies model usage.
        pass
