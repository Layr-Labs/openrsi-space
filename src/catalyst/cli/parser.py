import os
"""Argument definitions for the public solver commands."""
import argparse
from pathlib import Path

def build_parser():
    parser = argparse.ArgumentParser(description="Prepare harnesses, use local checks, and submit verified research to Yukon.")
    parser.add_argument("--state", default=os.environ.get("CATALYST_STATE", ".catalyst"),
                        help="Local state directory (default: .catalyst).")
    commands = parser.add_subparsers(dest="command", required=True)
    for kind in ("problem", "harness"):
        group = commands.add_parser(kind)
        sub = group.add_subparsers(dest="operation", required=True)
        if kind == "problem":
            sub.add_parser("list", help="List the pinned initial solver problems.")
            show = sub.add_parser("show")
            show.add_argument("id")
            clone = sub.add_parser("clone", help="Download a pinned problem and its local verifier.")
            clone.add_argument("id")
            clone.add_argument("output")
            for operation in ("setup", "check"):
                local = sub.add_parser(operation, help="Use the verifier in an ongoing research workspace.")
                local.add_argument("id")
                local.add_argument("--workspace", required=True)
        else:
            for operation in ("search", "inspect"):
                catalog = sub.add_parser(operation, help="Browse ranked public harnesses without a login.")
                if operation == "inspect":
                    catalog.add_argument("source", help="Immutable harness source SHA-256.")
                catalog.add_argument("--problem", default="ecdsa-fail")
                catalog.add_argument("--release")
                catalog.add_argument("--problem-version", help="Exact problem manifest SHA-256.")
                catalog.add_argument("--max-credits", type=float)
                catalog.add_argument("--model")
                catalog.add_argument("--q", help="Search public harness titles and descriptions.")
                catalog.add_argument("--sort", choices=["score", "credits"], default="score")
                catalog.add_argument("--limit", type=int, default=20)
                catalog.add_argument("--cursor")
            download = sub.add_parser("download", help="Download published harness source without login or execution.")
            download.add_argument("id", help="Evaluation UUID from the catalog.")
            download.add_argument("--output", required=True)
            download.add_argument("--source-sha256", help="Require the source hash returned by the ranking.")
            create = sub.add_parser("create", help="Create an editable harness source directory.")
            create.add_argument("id")
            create.add_argument("--title")
            create.add_argument("--output")
            create.add_argument("--agent", help=argparse.SUPPRESS)
            create.add_argument("--from", dest="source", help="Derive a new harness from an existing package.")
            create.add_argument("--executable", action="store_true",
                                help="Create editable agent source with a Docker build and entrypoint.")
            build = sub.add_parser("build", help="Build an immutable executable source snapshot locally.")
            build.add_argument("package")
            smoke = sub.add_parser("smoke", help="Run a built harness offline on a copied workspace.")
            smoke.add_argument("build_id")
            smoke.add_argument("--workspace", required=True)
            smoke.add_argument("--problem", help="Initial problem ID for the smoke-test task input.")
            smoke.add_argument("--timeout", type=int, default=120)
    local = commands.add_parser("local", help="Run your harness locally with Dungeness; no hosted service or Yukon login.")
    local_sub = local.add_subparsers(dest="operation", required=True)
    local_run = local_sub.add_parser("run", help="Build, prepare, and run a harness with metered local model access.")
    local_run.add_argument("package", help="Harness source directory.")
    local_run.add_argument("--dungeness", required=True, help="Clean checkout of the public Dungeness runtime.")
    local_run.add_argument("--problem", default="ecdsa.fail")
    local_run.add_argument("--provider")
    local_run.add_argument("--model")
    local_run.add_argument("--reasoning-effort", choices=["low", "medium", "high", "xhigh", "max"])
    local_run.add_argument("--budget", type=float, help="Normalized model-credit cap; may overshoot for an in-flight response.")
    local_run_tokens = local_run.add_mutually_exclusive_group()
    local_run_tokens.add_argument("--max-tokens", type=int)
    local_run_tokens.add_argument("--no-token-limit", action="store_true", help="Disable a token ceiling; retain the credit and time limits.")
    local_run.add_argument("--max-seconds", type=int)
    local_run.add_argument("--pricing", help="Optional trusted local pricing JSON; defaults to Catalyst's pinned schedule.")
    local_run.add_argument("--prepare-only", action="store_true", help="Build and prepare the run without reading credentials or calling models.")
    local_access = local_run.add_mutually_exclusive_group()
    local_access.add_argument("--grok-auth-file", nargs="?", const=str(Path.home() / ".grok/auth.json"),
                             help="Use a temporary Grok CLI subscription session; refresh credentials stay local.")
    local_access.add_argument("--codex-auth-file", nargs="?", const=str(Path.home() / ".codex/auth.json"),
                              help="Use temporary access from your local Codex login; refresh credentials stay outside the run.")
    local_access.add_argument("--provider-token-env", metavar="NAME",
                              help="Read an API token from this environment variable; never pass the token as an argument.")
    local_access.add_argument("--provider-access-file", help="Private provider credential map for an ensemble.")
    commands.add_parser("yukon-setup", help="Download the pinned ecdsa.fail workspace for Yukon.")
    commands.add_parser("yukon-run", help="Trusted remote evaluation bridge invoked by Yukon.")
    yukon_submit = commands.add_parser("yukon-submit", help="Submit a receipt through stock Yukon and bind its Pareto execution.")
    yukon_submit.add_argument("benchmark", nargs="?")
    yukon_submit.add_argument("--note-file", required=True)
    yukon_submit.add_argument("--model", required=True)
    yukon_submit.add_argument("--harness", required=True)
    dependencies = yukon_submit.add_mutually_exclusive_group(required=True)
    dependencies.add_argument("--no-dependencies", action="store_true")
    dependencies.add_argument("--dependencies-file")
    yukon_bind = commands.add_parser("yukon-bind", help="Resume execution binding for an already submitted Yukon job.")
    yukon_bind.add_argument("--job-id", required=True)
    yukon_bind.add_argument("--benchmark-id", required=True)
    remote = commands.add_parser("remote", help="Submit to and inspect the verification service directly.")
    remote_sub = remote.add_subparsers(dest="operation", required=True)
    remote_submit = remote_sub.add_parser("submit", help="Upload harness source and queue one evaluation.")
    remote_submit.add_argument("package", help="Path to your harness source directory.")
    remote_submit.add_argument("--wait", action="store_true", help="Wait, validate the result and save its verification reference.")
    remote_submit.add_argument("--source-license",
                               help="Optional license you have authority to grant for public source. Omission grants no additional license.")
    remote_submit.add_argument("--entrypoint", help="Launch argv for an existing repository without harness.json; parsed without a shell.")
    remote_submit.add_argument("--dockerfile", help="Relative build recipe for --entrypoint (default: Dockerfile).")
    remote_submit.add_argument("--provider", help="Model provider; use with --model (for example, kimi-code).")
    remote_submit.add_argument("--model", help="Exact declared model name; prices are resolved before execution (for example, k3).")
    remote_submit.add_argument("--reasoning-effort", choices=["low", "medium", "high", "xhigh", "max"])
    remote_submit.add_argument("--budget", type=float, help="Run spending cap in normalized model credits.")
    remote_submit_tokens = remote_submit.add_mutually_exclusive_group()
    remote_submit_tokens.add_argument("--max-tokens", type=int, help="Override the run's model-token cap.")
    remote_submit_tokens.add_argument("--no-token-limit", action="store_true", help="Disable a token ceiling; retain the credit and time limits.")
    remote_submit.add_argument("--max-seconds", type=int, help="Override the run's wall-time cap.")
    token_input = remote_submit.add_mutually_exclusive_group()
    token_input.add_argument("--provider-access-file",
                             help="Authorize remote use of your model accounts via a private credential map; never package it.")
    token_input.add_argument("--grok-auth-file", nargs="?", const=str(Path.home() / ".grok/auth.json"),
                             help="Use a temporary Grok CLI subscription session; refresh credentials stay local.")
    token_input.add_argument("--codex-auth-file", nargs="?", const=str(Path.home() / ".codex/auth.json"),
                             help="Authorize remote use of your ChatGPT allowance; send temporary Codex access, keeping refresh credentials local.")
    token_input.add_argument("--prompt-model-token", action="store_true",
                             help="Authorize remote use of your model account with a token entered at a hidden prompt.")
    token_input.add_argument("--model-token-stdin", action="store_true",
                             help="Authorize remote use of your model account with one private provider-token line from stdin.")
    renewal = remote_sub.add_parser("renew-access", help="Replace temporary access for an owned queued evaluation.")
    renewal.add_argument("id")
    renewal_input = renewal.add_mutually_exclusive_group(required=True)
    renewal_input.add_argument("--grok-auth-file", nargs="?", const=str(Path.home() / ".grok/auth.json"),
                             help="Use a temporary Grok CLI subscription session; refresh credentials stay local.")
    renewal_input.add_argument("--codex-auth-file", nargs="?", const=str(Path.home() / ".codex/auth.json"))
    renewal_input.add_argument("--provider-access-file")
    renewal_input.add_argument("--prompt-model-token", action="store_true")
    renewal_input.add_argument("--model-token-stdin", action="store_true")
    for operation, help_text in (
        ("status", "Read the current status of a submitted evaluation."),
        ("wait", "Wait for an existing evaluation; never enqueue another run."),
        ("cancel", "Cancel an owned evaluation; running processes stop before cancellation completes."),
    ):
        remote_action = remote_sub.add_parser(operation, help=help_text)
        remote_action.add_argument("id", help="Evaluation UUID returned by submit.")
    for operation in ("artifacts", "sharing"):
        action = remote_sub.add_parser(operation, help="Inspect artifact downloads or sharing for an owned run.")
        action.add_argument("id")
    download = remote_sub.add_parser("download", help="Download the evaluated harness source with checksum verification.")
    download.add_argument("id")
    download.add_argument("--kind", choices=["harness"], default="harness")
    download.add_argument("--output", required=True)
    for operation in ("publish",):
        action = remote_sub.add_parser(operation, help="Publish historical harness source or add a source license.")
        action.add_argument("id")
        action.add_argument("--harness", action="store_true")
        if operation == "publish":
            action.add_argument("--license", help="Source license; preserves existing third-party notices.")
            action.add_argument("--confirm-source-reviewed", action="store_true",
                                help="Confirm review of the exact source bundle and responsibility for its public release; credential screening still applies.")
    return parser, commands
