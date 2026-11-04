from __future__ import annotations
from openrsi_space.compatibility import FUNDING_PROTOCOL

import argparse
import json
import os
from pathlib import Path
import sys
from openrsi_space.common import (
    OpenRSIError, extract_bundle, identifier, now,
    read_json, snapshot_directory, write_json,
)


from . import parser as argument_parser

def create_harness(args):
    if args.agent:
        raise OpenRSIError("Bundled agents are retired. Create an executable harness "
                            "with a Dockerfile and entrypoint; install your coding agent inside it.")
    if args.executable and (args.agent or args.source):
        raise OpenRSIError("--executable cannot be combined with --agent or --from.")
    identity = identifier(args.id)
    target = Path(args.output or identity).resolve()
    if target.exists():
        raise OpenRSIError(f"Directory already exists: {target}")
    derived = None
    if args.source:
        snapshot, content = snapshot_directory(Path(args.source))
        if snapshot["kind"] != "harness":
            raise OpenRSIError("--from requires a harness package.")
        if "execution" not in snapshot["document"]:
            raise OpenRSIError("This legacy harness selects a bundled agent. Migrate it "
                                "to openrsi-exec-v1 with a Dockerfile and entrypoint.")
        extract_bundle(content, target)
        document = read_json(target / "harness.json")
        derived = {k: snapshot[k] for k in ("id", "version")}
        document.update({"id": identity, "title": args.title or identity, "created_at": now()})
    else:
        document = {
            "schema_version": 1, "kind": "harness", "id": identity, "title": args.title or identity,
            "description": "A reusable method and knowledge bundle.",
            "scope": "Describe the intended problems and any task-specific tuning.",
            "created_at": now(),
        }
        target.mkdir(parents=True)
        (target / "instructions.md").write_text(
            "# Method\n\nInspect the problem, form a hypothesis, implement it, and evaluate the result.\n"
            "Consult the supplied harness knowledge when useful. Record useful findings for the researcher.\n")
        (target / "knowledge").mkdir()
        (target / "knowledge" / "notes.md").write_text("# Reusable insights\n\nAdd findings, references, and methods here.\n")
    if not args.source:
        from openrsi_space.harnesses.executable import create_starter
        document.pop("agent", None)
        document["description"] = "An executable autonomous research harness."
        document["execution"] = create_starter(target)
    if derived:
        document["derived_from"] = derived
    write_json(target / "harness.json", document)
    print(target)


def model_access_input(args):
    if args.provider_access_file:
        from openrsi_space.credentials import encode_provider_access
        return encode_provider_access(read_json(Path(args.provider_access_file).expanduser()))
    if args.prompt_model_token:
        import getpass
        if not sys.stdin.isatty():
            raise OpenRSIError("Use a terminal for the hidden provider-token prompt.")
        return getpass.getpass("Provider API key (not saved): ")
    if args.model_token_stdin:
        from openrsi_space.credentials import MAX_TOKEN_BYTES, validate_token
        token = sys.stdin.readline(MAX_TOKEN_BYTES + 2).rstrip("\r\n")
        validate_token(token)
        return token
    return None


def model_access_notice(args, client, evaluation=None):
    if not any(getattr(args, name, None) for name in (
            "provider_access_file", "prompt_model_token", "model_token_stdin")):
        return
    budget = (f" Spending cap: {evaluation['max_model_credits']:g} normalized model credits."
              if evaluation is not None else " The existing run's limits still apply.")
    print(
        f"REMOTE MODEL ACCESS: You are sending your model credential to {client.base}. "
        "OpenRSI runs your agent on its remote server using YOUR model account; "
        "calls consume YOUR API credits. Subscription login handoffs are not supported. "
        "Use this credential option only if you authorize that remote use."
        + budget + " Normalized credits are not a guaranteed cash-billing limit. "
        "Your Yukon key is separate and does not fund model calls.",
        file=sys.stderr, flush=True,
    )


def remote_command(args, state):
    if args.operation == 'funding-policy':
        from openrsi_space.client import transport
        result = json.loads(transport.fetch(transport.endpoint() + '/public/funding-policy', None, limit=65536))
        if not isinstance(result, dict) or result.get('protocol') != FUNDING_PROTOCOL:
            raise OpenRSIError('Evaluator returned an invalid funding policy.')
        print(json.dumps(result, indent=2))
        return
    if args.operation == 'build-policy':
        from openrsi_space.client.build_policy import policy
        print(json.dumps(policy(), indent=2))
        return
    if args.operation == 'limits':
        from openrsi_space.client.source_limits import policy, measure, check
        result = policy()
        if args.package is not None:
            from openrsi_space.client.evaluations import source_snapshot
            snapshot, archive = source_snapshot(args.package)
            result['local_source'] = measure(snapshot, archive)
            check(result['local_source'], result['max_expanded_source_bytes'], result['max_archive_bytes'])
            result['within_size_limits'] = True
        print(json.dumps(result, indent=2))
        return
    from openrsi_space.client.evaluations import RemoteClient
    client = RemoteClient(state)
    if args.operation == 'funding':
        from openrsi_space.client import transport
        print(json.dumps(json.loads(transport.solver_fetch(client.base, '/funding', client.bearer)), indent=2))
        return
    if args.operation == "logs":
        print(json.dumps(client.logs(args.id, args.output), indent=2))
        return
    if args.operation == "diagnostics":
        print(json.dumps(client.diagnostics(args.id, args.output), indent=2))
        return
    if args.operation == "cancel":
        print(json.dumps(client.cancel(args.id), indent=2))
        return
    if args.operation in {"artifacts", "download", "sharing", "publish"}:
        if args.operation == "artifacts":
            result = client.artifacts(args.id)
        elif args.operation == "download":
            result = client.download_artifact(args.id, args.kind, args.output)
        elif args.operation == "sharing":
            result = client.sharing(args.id)
        else:
            if not args.harness:
                raise OpenRSIError("Select --harness explicitly.")
            changes = {"harness": True}
            if args.operation == "publish":
                if args.harness and not args.confirm_source_reviewed:
                    raise OpenRSIError(
                        "Download and review the exact harness bundle for private source, secrets and third-party "
                        "rights, then use --confirm-source-reviewed. You are responsible for the material you "
                        "choose to publish. Credential screening cannot be waived."
                    )
                if args.license:
                    changes["license"] = args.license
            result = client.sharing(args.id, changes)
        print(json.dumps(result, indent=2))
        return
    if args.operation == "submit":
        from openrsi_space.publication import publication_choices
        publication = publication_choices({
            "harness": True, "traces": False, "license": args.source_license}, require_public=True)
        print("Harness source will be PUBLIC after this run stops and publication screening passes. "
              "Public source is required; review your files and third-party rights before submitting. "
              "Traces are retained internally.", file=sys.stderr, flush=True)
        execution = None
        if args.entrypoint is not None:
            import shlex
            execution = {"interface": "openrsi-exec-v1", "dockerfile": args.dockerfile or "Dockerfile",
                         "entrypoint": shlex.split(args.entrypoint)}
        elif args.dockerfile is not None:
            raise OpenRSIError("--dockerfile requires --entrypoint.")
        overrides = {key: getattr(args, key) for key in (
            "provider", "model", "reasoning_effort", "budget", "max_tokens", "max_seconds"
        ) if getattr(args, key) is not None}
        if args.no_token_limit:
            overrides["max_tokens"] = None
        if args.platform_funded:
            overrides["platform_funded"] = True
        # Validate choices before asking the solver for a credential.
        from openrsi_space.client.configuration import evaluation_config
        config = evaluation_config(Path(args.package) / "evaluation.json", overrides, check_pricing=False)
        from openrsi_space.credentials import require_remote_models
        from openrsi_space.contracts.accounting import evaluation_models
        require_remote_models(evaluation_models(config))
        from openrsi_space.credentials import platform_access
        if platform_access(config):
            if any(getattr(args, key, None) for key in ("provider_access_file", "prompt_model_token", "model_token_stdin")):
                raise OpenRSIError("Platform-funded submissions must not include personal model credentials.")
            print("Platform-funded inference: no personal model credential will be read or transferred. "
                  "Admission is subject to your account allowance and the platform funding policy.", file=sys.stderr, flush=True)
        for credential_file in (args.provider_access_file,):
            if credential_file and Path(credential_file).expanduser().resolve().is_relative_to(
                    Path(args.package).resolve()):
                raise OpenRSIError("Keep credential files outside the submitted source directory.")
        from openrsi_space.client.evaluations import request_body
        from openrsi_space.client.local_check import check_submission
        body = request_body(Path(args.package), client.base, evaluation_overrides=overrides,
                            execution=execution, publication=publication,
                            problem_release=args.problem_release, check_pricing=False)
        local_check = check_submission(state, Path(args.package), body, client.base,
                                       local_run=args.local_run)
        print(f"Local Dungeness check: {local_check['status']}" +
              (f" ({local_check['run_id']})" if 'run_id' in local_check else ""),
              file=sys.stderr, flush=True)
        model_access_notice(args, client, config)
        model_token = model_access_input(args)
        try:
            accepted = client.submit(Path(args.package), **(
                {"model_token": model_token} if model_token is not None else {}),
                **({"evaluation_overrides": overrides} if overrides else {}),
                **({"execution": execution} if execution else {}),
                **({"problem_release": args.problem_release} if args.problem_release else {}),
                publication=publication, local_check=local_check)
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
            "reason", "error", "progress", "diagnostics",
        ) if key in result}, indent=2))
    else:
        print(f"Remote evaluation {identity}", file=sys.stderr, flush=True)
        try:
            artifact = client.wait(identity)
        except KeyboardInterrupt:
            raise OpenRSIError(
                f"Stopped waiting; the remote job continues. Resume with openrsi-space remote wait {identity} "
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


def dispatch(args):
    state = Path(args.state).expanduser().resolve()
    try:
        if args.command == "problem":
            from openrsi_space.challenge.catalog import clone_problem, develop, get_problem, initial_problems
            if args.operation == "current":
                from openrsi_space.client.catalog import PublicCatalog
                current = PublicCatalog().current_problem()
                print(json.dumps(current, indent=2))
                if not current["installed"]:
                    raise OpenRSIError("Update the OpenRSI checkout/package to match the active evaluator release before preparing or submitting a new run.")
            elif args.operation == "list":
                print(json.dumps(initial_problems(), indent=2))
            elif args.operation == "show":
                print(json.dumps(get_problem(args.id, release=args.problem_release), indent=2))
            elif args.operation == "clone":
                print(json.dumps(clone_problem(args.id, Path(args.output).resolve()), indent=2))
            else:
                return develop(args.id, Path(args.workspace), args.operation)
        elif args.command == "harness":
            if args.operation in {"search", "inspect", "download"}:
                from openrsi_space.client.catalog import PublicCatalog
                client = PublicCatalog()
                if args.operation == "download":
                    result = client.download(args.id, args.output, source_sha256=args.source_sha256)
                else:
                    filters = {k: getattr(args, k) for k in (
                        "problem", "release", "problem_version", "max_credits", "model", "q", "sort", "limit", "cursor")}
                    result = client.search(source=args.source if args.operation == "inspect" else None, **filters)
                print(json.dumps(result, indent=2))
            elif args.operation == "create":
                create_harness(args)
            else:
                from openrsi_space.harnesses.executable import build, smoke
                if args.operation == "build":
                    print(json.dumps(build(state, Path(args.package).resolve()), indent=2))
                else:
                    from openrsi_space.challenge.catalog import get_problem
                    problem = get_problem(args.problem) if args.problem else None
                    result = smoke(state, args.build_id, Path(args.workspace), problem=problem,
                                   timeout=args.timeout)
                    print(json.dumps(result, indent=2))
                    return 0 if result["status"] == "completed" else 1
        elif args.command == "local":
            from openrsi_space.integrations.dungeness.local import run
            return run(args, state)
        elif args.command == "yukon-setup":
            from openrsi_space.integrations.yukon.authentication import setup_problems
            setup_problems(Path.cwd())
        elif args.command == "yukon-run":
            from openrsi_space.integrations.yukon.receipts import check_receipt
            check_receipt()
        elif args.command == "yukon-submit":
            from openrsi_space.integrations.yukon.submission import submit
            print(json.dumps(submit(
                Path.cwd(), note_file=args.note_file, model=args.model, harness=args.harness,
                dependencies_file=args.dependencies_file, no_dependencies=args.no_dependencies,
                benchmark=args.benchmark), indent=2))
        elif args.command == "yukon-bind":
            from openrsi_space.integrations.yukon.submission import bind_job
            print(json.dumps(bind_job(Path.cwd(), args.job_id, args.benchmark_id), indent=2))
        elif args.command == "remote":
            remote_command(args, state)
        return 0
    except (OpenRSIError, OSError, KeyError, ValueError) as error:
        print(f"openrsi-space: {error}", file=sys.stderr)
        return 1


def main(argv=None):
    parser, _ = argument_parser.build_parser()
    return dispatch(parser.parse_args(argv))
