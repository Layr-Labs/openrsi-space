"""Compatibility with pinned runtimes predating runtime-contract.json.

Do not add new capabilities here. Remove this bridge when operators retire the
pre-contract pins; current runtimes are checked only through their declaration.
"""
from pathlib import Path


MARKERS = {
    "command-harness-v1": (("src/dungeness/compiler.py", "def command_execution("),),
    "run-model-access-v1": (("dungeness", '    "model_access",\n'),),
    "priced-model-requests-v1": (("services/gateway/gateway_models.py", "def validate_declared_request("),),
    "command-exit-status-v1": (("adapters/harbor/command_agent.py", "result.return_code"),),
    "rejected-request-accounting-v1": (("services/gateway/gateway_runtime.py", "def rejected_before_generation("),),
    "assigned-problem-service-v1": (
        ("src/dungeness/compiler.py", "def resolve_problem_service("),
        ("services/gateway/gateway.py", "async def assigned_task("),
        ("services/gateway/gateway.py", "async def assigned_file("),
        ("services/gateway/gateway.py", "async def assigned_resource("),
    ),
    "optional-model-token-limit-v1": (("dungeness", "--no-model-token-limit"),),
}


def supports(root: Path, capability: str) -> bool:
    markers = MARKERS.get(capability)
    if markers is None:
        return False
    for relative, marker in markers:
        try:
            if marker not in (root / relative).read_text():
                return False
        except (OSError, UnicodeError):
            return False
    return True
