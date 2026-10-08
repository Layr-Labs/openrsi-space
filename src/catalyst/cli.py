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
    if args.task:
        if not args.checkpoint:
            raise CatalystError("--task requires --checkpoint.")
        from .dungeness import installation, native_problem
        execution, metric, instructions = native_problem(
            Path(installation(state)["path"]), args.task, args.checkpoint)
    else:
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
    if not args.task:
        (target / "source").mkdir()
        (target / "source" / "solution.py").write_text(templates.SOLUTION)
        (target / "source" / "check.py").write_text(templates.CHECKER)
        (target / "verifier").mkdir()
        for filename, text in (("Dockerfile", templates.DOCKERFILE),
                               ("grade.py", templates.GRADE), ("test.sh", templates.TEST_SH)):
            (target / "verifier" / filename).write_text(text)
    print(target)
    if not args.task:
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


def remote_command(args, state):
    from .remote import RemoteClient
    client = RemoteClient(state)
    if args.operation == "submit":
        model_token = None
        if args.codex_auth_file:
            from .live_provider import encode_codex_access
            model_token = encode_codex_access(args.codex_auth_file)
        elif args.prompt_model_token:
            import getpass
            if not sys.stdin.isatty():
                raise CatalystError("Use a terminal for the hidden provider-token prompt.")
            model_token = getpass.getpass("Provider access token (not saved): ")
        elif args.model_token_stdin:
            from .model_access import MAX_TOKEN_BYTES, validate_token
            model_token = sys.stdin.readline(MAX_TOKEN_BYTES + 2).rstrip("\r\n")
            validate_token(model_token)
        try:
            accepted = client.submit(Path(args.package), **(
                {"model_token": model_token} if model_token is not None else {}))
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


def main(argv=None):
    parser = argparse.ArgumentParser(description="Research locally; evaluate with Dungeness; publish and compare evidence.")
    parser.add_argument("--state", default=os.environ.get("CATALYST_STATE", ".catalyst"),
                        help="Local state directory (default: .catalyst).")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Pin an existing clean Dungeness checkout.")
    init.add_argument("--dungeness", required=True)
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
            create.add_argument("--task", help="An existing fully qualified Dungeness task.")
            create.add_argument("--checkpoint")
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
    evaluate = commands.add_parser("evaluate", help="Freeze inputs and evaluate them through Dungeness.")
    evaluate.add_argument("problem")
    evaluate.add_argument("harness")
    evaluate.add_argument("--budget", type=float, required=True)
    evaluate.add_argument("--max-tokens", type=int, default=100000)
    evaluate.add_argument("--resume", help="Continue from a retained Catalyst evaluation.")
    evaluate.add_argument("--env-file", help="Credential file used by Dungeness; never included in publications.")
    evaluate.add_argument("--prepare-only", action="store_true", help="Prepare inputs without starting containers or making model calls.")
    evaluate.add_argument("--build", help="Built executable harness ID.")
    evaluate.add_argument("--model", help="Explicit upstream OpenAI model for an executable harness.")
    evaluation = commands.add_parser("evaluation")
    sub = evaluation.add_subparsers(dest="operation", required=True)
    for operation in ("execute", "import", "publish", "show"):
        action = sub.add_parser(operation)
        action.add_argument("id")
        if operation == "publish":
            action.add_argument("--server")
            action.add_argument("--include-trace", action="store_true")
    imported = commands.add_parser("import-run", help="Associate an existing canonical Dungeness record with package snapshots.")
    imported.add_argument("record")
    imported.add_argument("--problem", required=True)
    imported.add_argument("--harness", required=True)
    imported.add_argument("--id")
    imported.add_argument("--starting-cost", type=float, help="Known ancestor cost for an imported continuation.")
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
    remote = commands.add_parser("remote", help="Submit to and inspect the verification service directly.")
    remote_sub = remote.add_subparsers(dest="operation", required=True)
    remote_submit = remote_sub.add_parser("submit", help="Upload harness source and queue one evaluation.")
    remote_submit.add_argument("package", nargs="?", default="submission", help="Harness directory (default: submission).")
    remote_submit.add_argument("--wait", action="store_true", help="Wait, validate the result and save its verification reference.")
    token_input = remote_submit.add_mutually_exclusive_group()
    token_input.add_argument("--codex-auth-file", nargs="?", const=str(Path.home() / ".codex/auth.json"),
                             help="Send temporary ChatGPT access from Codex login; keep refresh credentials local.")
    token_input.add_argument("--prompt-model-token", action="store_true",
                             help="Read a provider token from a hidden terminal prompt; never save it.")
    token_input.add_argument("--model-token-stdin", action="store_true",
                             help="Read one provider-token line from stdin; never save it.")
    for operation, help_text in (
        ("status", "Read the current status of a submitted evaluation."),
        ("wait", "Wait for an existing evaluation; never enqueue another run."),
        ("traces", "Download the owner's private trace archive."),
    ):
        remote_action = remote_sub.add_parser(operation, help=help_text)
        remote_action.add_argument("id", help="Evaluation UUID returned by submit.")
    local_init = commands.add_parser("local-evaluator-init", help="Create an isolated mock-provider integration workspace.")
    local_init.add_argument("directory")
    local_init.add_argument("--dungeness", required=True)
    local_init.add_argument("--base-image", default="python:3.12-slim-bookworm")
    real_init = commands.add_parser("local-ecdsa-init", help="Configure the real pinned ECDSA task with model access disabled.")
    real_init.add_argument("directory")
    real_init.add_argument("--dungeness", required=True)
    remote_init = commands.add_parser("remote-evaluator-init", help="Provision a private VM service with model access disabled.")
    remote_init.add_argument("directory")
    remote_init.add_argument("--dungeness", required=True)
    remote_init.add_argument("--owner-id", required=True, help="Yukon solver account UUID bound to the provisioned key.")
    login_config = commands.add_parser("yukon-auth-configure", help="Enable Yukon login for model-disabled remote evaluations.")
    login_config.add_argument("--auth-file", required=True)
    login_config.add_argument("--worker-config", required=True)
    login_config.add_argument("--yukon-api", required=True, help="Trusted HTTPS Yukon API origin.")
    github_config = commands.add_parser("github-configure", help="Authorize the challenge's GitHub workflow for receipt retrieval.")
    github_config.add_argument("--auth-file", required=True)
    github_config.add_argument("--repository", required=True)
    github_config.add_argument("--repository-id", required=True)
    github_config.add_argument("--yukon-api", required=True)
    github_config.add_argument("--baseline-evaluation", required=True)
    github_config.add_argument("--baseline-sha", required=True)
    github_config.add_argument("--benchmark-id", help="Add after Yukon assigns the imported benchmark UUID.")
    evaluator = commands.add_parser("evaluator-serve", help="Run the API and its supervised worker.")
    evaluator.add_argument("--local-auth", "--local-test", "--service-auth", action="store_true", required=True,
                           help="Use the identities configured in the auth file.")
    evaluator.add_argument("--auth-file", required=True)
    evaluator.add_argument("--problem-set", required=True)
    evaluator.add_argument("--worker-config", help="Worker configuration (default: worker.json beside --auth-file).")
    evaluator.add_argument("--port", type=int, default=8777)
    worker = commands.add_parser("worker", help="Process jobs through the local-test Dungeness worker.")
    worker.add_argument("--local-auth", "--local-test", action="store_true", required=True)
    worker.add_argument("--config", required=True)
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--supervisor-fd", type=int, help=argparse.SUPPRESS)
    worker.add_argument("--credential-fd", type=int, help=argparse.SUPPRESS)
    registration = commands.add_parser("local-submission-bind", help="Register a trusted local queued-submission fixture.")
    registration.add_argument("evaluation_id")
    registration.add_argument("--owner", required=True)
    registration.add_argument("--repository", required=True)
    registration.add_argument("--commit", required=True)
    args = parser.parse_args(argv)
    state = Path(args.state).expanduser().resolve()
    try:
        if args.command == "init":
            from .dungeness import configure
            print(json.dumps(configure(state, Path(args.dungeness)), indent=2))
        elif args.command == "problem":
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
        elif args.command == "evaluate":
            from .dungeness import prepare, execute, import_evaluation
            meta = prepare(state, Path(args.problem).resolve(), Path(args.harness).resolve(),
                           args.budget, args.max_tokens, args.resume, args.env_file,
                           build_id=args.build, model=args.model)
            print("Prepared evaluation:", meta["id"], flush=True)
            if args.prepare_only:
                print(meta["spec_path"])
            else:
                code = execute(state, meta["id"])
                if Path(meta["record_path"]).is_file():
                    print(import_evaluation(state, meta["id"]))
                return code
        elif args.command == "evaluation":
            from .dungeness import execute, import_evaluation
            identifier(args.id)
            folder = state / "evaluations" / args.id
            if args.operation == "show":
                print(json.dumps(read_json(folder / "evaluation.json"), indent=2))
            elif args.operation == "execute":
                code = execute(state, args.id)
                meta = read_json(folder / "evaluation.json")
                if Path(meta["record_path"]).is_file():
                    print(import_evaluation(state, args.id))
                return code
            elif args.operation == "import":
                print(import_evaluation(state, args.id))
            else:
                target = import_evaluation(state, args.id)
                for kind in ("problem", "harness"):
                    publish_content(state, args.server, (folder / f"{kind}.zip").read_bytes())
                record_path = Path(read_json(folder / "evaluation.json")["record_path"])
                print(json.dumps(publish_content(state, args.server,
                                                publication_bundle(target, args.include_trace, record_path))))
        elif args.command == "import-run":
            from .dungeness import normalize_run
            problem, pzip = snapshot_directory(Path(args.problem).resolve())
            harness, hzip = snapshot_directory(Path(args.harness).resolve())
            raw = read_json(Path(args.record))
            resumed = bool(raw.get("relations", {}).get("resumed_from"))
            cost = args.starting_cost if resumed else 0
            doc = normalize_run(Path(args.record).resolve(), problem, harness, identity=args.id, starting_cost=cost)
            target = state / "runs" / doc["id"]
            if target.exists():
                raise CatalystError("Imported run ID already exists; use a new --id.")
            write_json(target / "run.json", doc)
            (target / "dungeness-record.json").write_bytes(Path(args.record).read_bytes())
            snapshots = state / "imports" / doc["id"]
            snapshots.mkdir(parents=True)
            (snapshots / "problem.zip").write_bytes(pzip)
            (snapshots / "harness.zip").write_bytes(hzip)
            write_json(snapshots / "import.json", {"record_path": str(Path(args.record).resolve())})
            print(target)
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
        elif args.command == "remote":
            remote_command(args, state)
        elif args.command == "local-evaluator-init":
            from .local_run import initialize
            print(json.dumps(initialize(Path(args.directory), Path(args.dungeness), args.base_image)))
        elif args.command == "local-ecdsa-init":
            from .local_run import initialize_ecdsa
            print(json.dumps(initialize_ecdsa(Path(args.directory), Path(args.dungeness))))
        elif args.command == "remote-evaluator-init":
            from .hosted import initialize_remote
            print(json.dumps(initialize_remote(Path(args.directory), Path(args.dungeness), args.owner_id), indent=2))
        elif args.command == "yukon-auth-configure":
            from .yukon_auth import configure_yukon_login
            print(json.dumps(configure_yukon_login(Path(args.auth_file).resolve(), args.yukon_api,
                                                   Path(args.worker_config).resolve()), indent=2))
        elif args.command == "github-configure":
            from .evaluator import JobStore
            from .hosted import configure_github
            print(json.dumps(configure_github(
                JobStore(state), Path(args.auth_file).resolve(), repository=args.repository,
                repository_id=args.repository_id, yukon_api=args.yukon_api,
                baseline_evaluation=args.baseline_evaluation, baseline_sha=args.baseline_sha,
                benchmark_id=args.benchmark_id), indent=2))
        elif args.command == "evaluator-serve":
            from .evaluator import serve
            serve(state, Path(args.auth_file), Path(args.problem_set), args.port,
                  Path(args.worker_config) if args.worker_config else None)
        elif args.command == "worker":
            from .worker import work
            work(state, Path(args.config), once=args.once, supervisor_fd=args.supervisor_fd,
                 credential_fd=args.credential_fd)
        elif args.command == "local-submission-bind":
            from .evaluator import JobStore
            JobStore(state).register_submission(args.evaluation_id, args.owner, args.repository, args.commit)
            print("Registered local queued-submission fixture.")
        return 0
    except (CatalystError, OSError, KeyError, ValueError) as error:
        print(f"catalyst: {error}", file=sys.stderr)
        return 1


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
