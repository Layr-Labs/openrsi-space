from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .catalog import Catalog
from .common import (
    CatalystError, canonical, extract_bundle, identifier, make_bundle, now,
    open_bundle, read_json, snapshot_directory, write_json,
)


def request(server, path, body=None, mime=None):
    target = server.rstrip("/") + path
    if not target.startswith(("http://", "https://")):
        raise CatalystError("Server must be an HTTP(S) URL.")
    try:
        req = Request(target, data=body, headers={"Content-Type": mime} if mime else {})
        with urlopen(req, timeout=30) as response:
            return response.read()
    except HTTPError as error:
        try:
            message = json.loads(error.read())["error"]
        except (ValueError, KeyError):
            message = str(error)
        raise CatalystError(message) from error
    except URLError as error:
        raise CatalystError(f"Cannot reach the catalog: {error.reason}") from error


def create_problem(args, state):
    from . import templates
    identity = identifier(args.id)
    target = Path(args.output or f"problems/{identity}").resolve()
    if target.exists():
        raise CatalystError(f"Directory already exists: {target}")
    metric = {"name": args.metric, "direction": args.direction}
    instructions = templates.INSTRUCTIONS
    execution = {
        "repository": {"url": args.repository or "", "commit": args.commit or ""},
        "interface": "catalyst-file-v1", "candidate_paths": ["solution.py"],
        "verifier_include": ["check.py"], "timeout_sec": 900,
    }
    if args.metric != "score" or args.direction != "maximize":
        instructions = "# Research problem\n\nDescribe the objective and evaluation criteria here.\n"
    document = {
        "schema_version": 1, "kind": "problem", "id": identity, "title": args.title or identity,
        "description": "Edit this description to state the scientific objective.",
        "metric": metric, "created_at": now(), "execution": execution,
    }
    write_json(target / "problem.json", document)
    (target / "instructions.md").write_text(instructions)
    (target / "source").mkdir()
    (target / "source" / "solution.py").write_text(templates.SOLUTION)
    (target / "source" / "check.py").write_text(templates.CHECKER)
    (target / "verifier").mkdir()
    for filename, text in (("Dockerfile", templates.DOCKERFILE),
                           ("grade.py", templates.GRADE), ("test.sh", templates.TEST_SH)):
        (target / "verifier" / filename).write_text(text)
    print(target)
    print("Edit the package and pin its committed HTTPS source repository before a Dungeness evaluation.")


def create_harness(args):
    if args.executable and (args.agent or args.source):
        raise CatalystError("--executable cannot be combined with --agent or --from.")
    identity = identifier(args.id)
    target = Path(args.output or f"harnesses/{identity}").resolve()
    if target.exists():
        raise CatalystError(f"Directory already exists: {target}")
    derived = None
    if args.source:
        snapshot, content = snapshot_directory(Path(args.source))
        if snapshot["kind"] != "harness":
            raise CatalystError("--from requires a harness package.")
        extract_bundle(content, target)
        document = read_json(target / "harness.json")
        derived = {k: snapshot[k] for k in ("id", "version")}
        document.update({"id": identity, "title": args.title or identity, "created_at": now()})
        if args.agent:
            document["agent"] = args.agent
    else:
        document = {
            "schema_version": 1, "kind": "harness", "id": identity, "title": args.title or identity,
            "description": "A reusable method and knowledge bundle.",
            "scope": "Describe the intended problems and any task-specific tuning.",
            "agent": args.agent or "agent:projects/dungeness/codex-openai", "created_at": now(),
        }
        target.mkdir(parents=True)
        (target / "instructions.md").write_text(
            "# Method\n\nInspect the problem, form a hypothesis, implement it, and evaluate the result.\n"
            "Consult the supplied harness knowledge when useful. Record useful findings for the researcher.\n")
        (target / "knowledge").mkdir()
        (target / "knowledge" / "notes.md").write_text("# Reusable insights\n\nAdd findings, references, and methods here.\n")
    if args.executable:
        from .executable import create_starter
        document.pop("agent", None)
        document["description"] = "An executable autonomous research harness."
        document["execution"] = create_starter(target)
    if derived:
        document["derived_from"] = derived
    write_json(target / "harness.json", document)
    print(target)


def publish_content(state, server, content):
    if server:
        return json.loads(request(server, "/api/publish", content, "application/zip"))
    return Catalog(state / "catalog").publish(content)


def model_access_input(args):
    if args.codex_auth_file:
        from .credentials import encode_codex_access
        return encode_codex_access(args.codex_auth_file)
    if args.provider_access_file:
        from .credentials import encode_provider_access
        return encode_provider_access(read_json(Path(args.provider_access_file).expanduser()))
    if args.prompt_model_token:
        import getpass
        if not sys.stdin.isatty():
            raise CatalystError("Use a terminal for the hidden provider-token prompt.")
        return getpass.getpass("Provider access token (not saved): ")
    if args.model_token_stdin:
        from .credentials import MAX_TOKEN_BYTES, validate_token
        token = sys.stdin.readline(MAX_TOKEN_BYTES + 2).rstrip("\r\n")
        validate_token(token)
        return token
    return None


def model_access_notice(args, client, evaluation=None):
    if not any(getattr(args, name, None) for name in (
            "codex_auth_file", "provider_access_file", "prompt_model_token", "model_token_stdin")):
        return
    budget = (f" Spending cap: {evaluation['max_model_credits']:g} normalized model credits."
              if evaluation is not None else " The existing run's limits still apply.")
    print(
        f"REMOTE MODEL ACCESS: You are sending your model credential to {client.base}. "
        "Catalyst runs your agent on its remote server using YOUR model account; "
        "calls consume YOUR API credits or subscription allowance. "
        "Use this credential option only if you authorize that remote use."
        + budget + " Normalized credits are not a guaranteed cash-billing limit. "
        "Your Yukon key is separate and does not fund model calls.",
        file=sys.stderr, flush=True,
    )


def remote_command(args, state):
    from .remote import RemoteClient
    client = RemoteClient(state)
    if args.operation == "cancel":
        print(json.dumps(client.cancel(args.id), indent=2))
        return
    if args.operation == "renew-access":
        model_access_notice(args, client)
        token = model_access_input(args)
        try:
            print(json.dumps(client.renew_access(args.id, token), indent=2))
        finally:
            token = None
        return
    if args.operation in {"artifacts", "download", "sharing", "publish", "unpublish"}:
        if args.operation == "artifacts":
            result = client.artifacts(args.id)
        elif args.operation == "download":
            result = client.download_artifact(args.id, args.kind, args.output)
        elif args.operation == "sharing":
            result = client.sharing(args.id)
        else:
            if not (args.harness or args.traces):
                raise CatalystError("Select --harness and/or --traces explicitly.")
            changes = {kind: args.operation == "publish"
                       for kind in ("harness", "traces") if getattr(args, kind)}
            if args.operation == "publish":
                if args.harness and not args.license:
                    raise CatalystError("Publishing a harness requires --license.")
                if args.harness and not args.confirm_source_reviewed:
                    raise CatalystError(
                        "Download and review the exact harness bundle for private source, secrets and third-party "
                        "rights, then use --confirm-source-reviewed. You are responsible for the material you "
                        "choose to publish. Credential screening cannot be waived."
                    )
                if args.traces and not args.confirm_traces_reviewed:
                    raise CatalystError("Download/review sanitized traces, then use --confirm-traces-reviewed.")
                if args.license:
                    changes["license"] = args.license
                if args.traces:
                    changes["traces_reviewed"] = True
            result = client.sharing(args.id, changes)
        print(json.dumps(result, indent=2))
        return
    if args.operation == "submit":
        execution = None
        if args.entrypoint is not None:
            import shlex
            execution = {"interface": "catalyst-exec-v1", "dockerfile": args.dockerfile or "Dockerfile",
                         "entrypoint": shlex.split(args.entrypoint)}
        elif args.dockerfile is not None:
            raise CatalystError("--dockerfile requires --entrypoint.")
        overrides = {key: getattr(args, key) for key in (
            "provider", "model", "reasoning_effort", "budget", "max_tokens", "max_seconds"
        ) if getattr(args, key) is not None}
        # Validate choices before asking the solver for a credential.
        from .remote import evaluation_config
        config = evaluation_config(Path(args.package) / "evaluation.json", overrides, check_pricing=False)
        for credential_file in (args.codex_auth_file, args.provider_access_file):
            if credential_file and Path(credential_file).expanduser().resolve().is_relative_to(
                    Path(args.package).resolve()):
                raise CatalystError("Keep credential files outside the submitted source directory.")
        model_access_notice(args, client, config)
        model_token = model_access_input(args)
        try:
            accepted = client.submit(Path(args.package), **(
                {"model_token": model_token} if model_token is not None else {}),
                **({"evaluation_overrides": overrides} if overrides else {}),
                **({"execution": execution} if execution else {}))
        finally:
            model_token = None
        if not args.wait:
            print(json.dumps(accepted, indent=2))
            return
        identity = accepted["evaluation_id"]
    else:
        identity = args.id
    if args.operation == "status":
        result = client.status(identity)
        # Raw service responses may include private diagnostics.
        print(json.dumps({key: result[key] for key in (
            "evaluation_id", "status", "source_digest", "evidence_mode", "trace_available",
        ) if key in result}, indent=2))
    elif args.operation == "traces":
        print(json.dumps({"evaluation_id": identity, "traces": str(client.traces(identity))}, indent=2))
    else:
        print(f"Remote evaluation {identity}", file=sys.stderr, flush=True)
        try:
            artifact = client.wait(identity)
        except KeyboardInterrupt:
            raise CatalystError(
                f"Stopped waiting; the remote job continues. Resume with catalyst remote wait {identity} "
                "using the same --state directory."
            ) from None
        reference = client.export_reference(identity)
        print(json.dumps({
            "evaluation_id": identity, "status": "completed",
            "evidence_mode": artifact["metrics"]["evidenceMode"],
            **{key: artifact[key] for key in ("scores", "valid", "reason") if key in artifact},
            "judgment": str(client.folder(identity) / "judgment.json"),
            "verification": str(reference), "artifacts": str(client.folder(identity)),
        }, indent=2))


def build_parser():
    parser = argparse.ArgumentParser(description="Prepare harnesses, use local checks, and submit verified research to Yukon.")
    parser.add_argument("--state", default=os.environ.get("CATALYST_STATE", ".catalyst"),
                        help="Local state directory (default: .catalyst).")
    commands = parser.add_subparsers(dest="command", required=True)
    for kind in ("problem", "harness"):
        group = commands.add_parser(kind)
        sub = group.add_subparsers(dest="operation", required=True)
        create = sub.add_parser("create")
        create.add_argument("id")
        create.add_argument("--title")
        create.add_argument("--output")
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
            create.add_argument("--metric", default="score")
            create.add_argument("--direction", choices=["minimize", "maximize"], default="maximize")
            create.add_argument("--repository")
            create.add_argument("--commit")
        else:
            create.add_argument("--agent")
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
    publish = commands.add_parser("publish", help="Publish an immutable package snapshot to the catalog.")
    publish.add_argument("package")
    publish.add_argument("--server")
    publish.add_argument("--include-trace", action="store_true", help="Include raw records and traces, which may contain research contents.")
    fetch = commands.add_parser("fetch")
    fetch.add_argument("kind", choices=["problem", "harness", "run"])
    fetch.add_argument("id")
    fetch.add_argument("version")
    fetch.add_argument("--output", required=True)
    fetch.add_argument("--server")
    report = commands.add_parser("report", help="Attach an evidence concern; this does not label a harness as overfit.")
    report.add_argument("run_id")
    report.add_argument("run_version")
    report.add_argument("--body", required=True)
    report.add_argument("--supporting-run")
    report.add_argument("--server")
    serving = commands.add_parser("serve")
    serving.add_argument("--port", type=int, default=8765)
    commands.add_parser("demo", help="Add explicitly synthetic data without model calls.")
    commands.add_parser("list", help="List published snapshots.")
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
    remote_submit.add_argument("package", nargs="?", default="submission", help="Harness directory (default: submission).")
    remote_submit.add_argument("--wait", action="store_true", help="Wait, validate the result and save its verification reference.")
    remote_submit.add_argument("--entrypoint", help="Launch argv for an existing repository without harness.json; parsed without a shell.")
    remote_submit.add_argument("--dockerfile", help="Relative build recipe for --entrypoint (default: Dockerfile).")
    remote_submit.add_argument("--provider", help="Model provider; use with --model (for example, kimi-code).")
    remote_submit.add_argument("--model", help="Exact declared model name; prices are resolved before execution (for example, k3).")
    remote_submit.add_argument("--reasoning-effort", choices=["low", "medium", "high", "xhigh", "max"])
    remote_submit.add_argument("--budget", type=float, help="Run spending cap in normalized model credits.")
    remote_submit.add_argument("--max-tokens", type=int, help="Override the run's model-token cap.")
    remote_submit.add_argument("--max-seconds", type=int, help="Override the run's wall-time cap.")
    token_input = remote_submit.add_mutually_exclusive_group()
    token_input.add_argument("--provider-access-file",
                             help="Authorize remote use of your model accounts via a private credential map; never package it.")
    token_input.add_argument("--codex-auth-file", nargs="?", const=str(Path.home() / ".codex/auth.json"),
                             help="Authorize remote use of your ChatGPT allowance; send temporary Codex access, keeping refresh credentials local.")
    token_input.add_argument("--prompt-model-token", action="store_true",
                             help="Authorize remote use of your model account with a token entered at a hidden prompt.")
    token_input.add_argument("--model-token-stdin", action="store_true",
                             help="Authorize remote use of your model account with one private provider-token line from stdin.")
    renewal = remote_sub.add_parser("renew-access", help="Replace temporary access for an owned queued evaluation.")
    renewal.add_argument("id")
    renewal_input = renewal.add_mutually_exclusive_group(required=True)
    renewal_input.add_argument("--codex-auth-file", nargs="?", const=str(Path.home() / ".codex/auth.json"))
    renewal_input.add_argument("--provider-access-file")
    renewal_input.add_argument("--prompt-model-token", action="store_true")
    renewal_input.add_argument("--model-token-stdin", action="store_true")
    for operation, help_text in (
        ("status", "Read the current status of a submitted evaluation."),
        ("wait", "Wait for an existing evaluation; never enqueue another run."),
        ("traces", "Download the owner's private trace archive."),
        ("cancel", "Cancel an owned evaluation; running processes stop before cancellation completes."),
    ):
        remote_action = remote_sub.add_parser(operation, help=help_text)
        remote_action.add_argument("id", help="Evaluation UUID returned by submit.")
    for operation in ("artifacts", "sharing"):
        action = remote_sub.add_parser(operation, help="Inspect artifact downloads or sharing for an owned run.")
        action.add_argument("id")
    download = remote_sub.add_parser("download", help="Download a checksummed private evidence bundle.")
    download.add_argument("id")
    download.add_argument("--kind", choices=["complete", "harness", "traces"], default="complete")
    download.add_argument("--output", required=True)
    for operation in ("publish", "unpublish"):
        action = remote_sub.add_parser(operation, help="Explicitly publish or stop serving selected run artifacts.")
        action.add_argument("id")
        action.add_argument("--harness", action="store_true")
        action.add_argument("--traces", action="store_true")
        if operation == "publish":
            action.add_argument("--license", help="Source license; preserves existing third-party notices.")
            action.add_argument("--confirm-source-reviewed", action="store_true",
                                help="Confirm review of the exact source bundle and responsibility for its public release; credential screening still applies.")
            action.add_argument("--confirm-traces-reviewed", action="store_true",
                                help="Confirm that you reviewed the sanitized trace bundle for public release.")
    return parser, commands


def dispatch(args):
    state = Path(args.state).expanduser().resolve()
    try:
        if args.command == "problem":
            if args.operation == "create":
                create_problem(args, state)
            else:
                from .problems import clone_problem, develop, get_problem, initial_problems
                if args.operation == "list":
                    print(json.dumps(initial_problems(), indent=2))
                elif args.operation == "show":
                    print(json.dumps(get_problem(args.id), indent=2))
                elif args.operation == "clone":
                    print(json.dumps(clone_problem(args.id, Path(args.output).resolve()), indent=2))
                else:
                    return develop(args.id, Path(args.workspace), args.operation)
        elif args.command == "harness":
            if args.operation == "create":
                create_harness(args)
            else:
                from .executable import build, smoke
                if args.operation == "build":
                    print(json.dumps(build(state, Path(args.package).resolve()), indent=2))
                else:
                    from .problems import get_problem
                    problem = get_problem(args.problem) if args.problem else None
                    result = smoke(state, args.build_id, Path(args.workspace), problem=problem,
                                   timeout=args.timeout)
                    print(json.dumps(result, indent=2))
                    return 0 if result["status"] == "completed" else 1
        elif args.command == "publish":
            path = Path(args.package).resolve()
            record_path = None
            if args.include_trace and (path / "run.json").is_file():
                meta_path = state / "evaluations" / path.name / "evaluation.json"
                imported_path = state / "imports" / path.name / "import.json"
                if meta_path.is_file() or imported_path.is_file():
                    record_path = Path(read_json(meta_path if meta_path.is_file() else imported_path)["record_path"])
            print(json.dumps(publish_content(state, args.server,
                                            publication_bundle(path, args.include_trace, record_path))))
        elif args.command == "fetch":
            catalog = Catalog(state / "catalog") if not args.server else None
            if catalog:
                catalog.get(args.kind, args.id, args.version)
                content = catalog.bundle_path(args.kind, args.id, args.version).read_bytes()
            else:
                parts = "/".join(quote(p, safe="") for p in (args.kind, args.id, args.version))
                content = request(args.server, "/api/bundles/" + parts)
            print(json.dumps(extract_bundle(content, Path(args.output).resolve())))
        elif args.command == "report":
            doc = {"run_id": args.run_id, "run_version": args.run_version,
                   "body": args.body, "supporting_run": args.supporting_run}
            result = json.loads(request(args.server, "/api/reports", canonical(doc), "application/json")) if args.server else (
                Catalog(state / "catalog").report(args.run_id, args.run_version, args.body, args.supporting_run))
            print(json.dumps(result))
        elif args.command == "serve":
            from .server import serve
            serve(state / "catalog", args.port)
        elif args.command == "demo":
            from .demo import seed
            print(json.dumps(seed(Catalog(state / "catalog"))))
        elif args.command == "list":
            for obj in Catalog(state / "catalog").list():
                print(obj["kind"], obj["id"], obj["version"], obj["document"]["title"])
        elif args.command == "yukon-setup":
            from .yukon import setup_problems
            setup_problems(Path.cwd())
        elif args.command == "yukon-run":
            from .receipts import check_receipt
            check_receipt()
        elif args.command == "yukon-submit":
            from .yukon_submit import submit
            print(json.dumps(submit(
                Path.cwd(), note_file=args.note_file, model=args.model, harness=args.harness,
                dependencies_file=args.dependencies_file, no_dependencies=args.no_dependencies,
                benchmark=args.benchmark), indent=2))
        elif args.command == "yukon-bind":
            from .yukon_submit import bind_job
            print(json.dumps(bind_job(Path.cwd(), args.job_id, args.benchmark_id), indent=2))
        elif args.command == "remote":
            remote_command(args, state)
        return 0
    except (CatalystError, OSError, KeyError, ValueError) as error:
        print(f"catalyst: {error}", file=sys.stderr)
        return 1


def main(argv=None):
    parser, _ = build_parser()
    return dispatch(parser.parse_args(argv))


def publication_bundle(path: Path, include_trace=False, record_path: Path | None = None) -> bytes:
    if path.is_file():
        content = path.read_bytes()
        open_bundle(content)
        return content
    if (path / "run.json").is_file():
        files = {"run.json": canonical(read_json(path / "run.json"))}
        if include_trace:
            record = record_path or path / "dungeness-record.json"
            if record.is_file():
                files["dungeness-record.json"] = record.read_bytes()
            if record_path:
                events = record_path.parent / "usage" / "events.jsonl"
                if events.is_file():
                    files["trace/events.jsonl"] = events.read_bytes()
        return make_bundle(files)[1]
    snapshot, content = snapshot_directory(path)
    return content


if __name__ == "__main__":
    raise SystemExit(main())
