"""Local Dungeness runs with public model preflight; no Yukon login or receipts."""
from openrsi_space.compatibility import LEGACY_STATE, PROBLEM_DIGEST_LABEL, RUNTIME_NAMESPACE
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import uuid

from openrsi_space.common import OpenRSIError, canonical, extract_bundle, now, read_json, snapshot_directory, write_json
from openrsi_space.harnesses import executable
from openrsi_space.integrations.dungeness.agent import install_agent, model_profile
from openrsi_space.challenge.catalog import get_problem, problem_statement, initial_problems
from openrsi_space.contracts.results import digest
from openrsi_space.challenge.preparation import install_task, require_problem_service_runtime, write_yaml
from openrsi_space.contracts.accounting import evaluation_models, pricing_schedule
from openrsi_space.credentials import provider_environment


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
    if result.returncode:
        raise OpenRSIError(result.stderr.strip() or 'Git command failed.')
    return result.stdout.strip()


def validate_credential_locations(args):
    package = Path(args.package).resolve()
    for name in ('codex_auth_file', 'grok_auth_file', 'provider_access_file'):
        path = getattr(args, name, None)
        if path and Path(path).expanduser().resolve().is_relative_to(package):
            raise OpenRSIError('Keep model credential files outside the harness source directory.')


def credential_input(args, providers):
    from openrsi_space.credentials import (decode_codex_access, encode_codex_access, validate_provider_access,
                                      grok_access, LOCAL_SESSION_ENV)
    validate_credential_locations(args)
    if args.codex_auth_file:
        access = {'openai-chatgpt': decode_codex_access(encode_codex_access(args.codex_auth_file))}
    elif getattr(args, 'grok_auth_file', None):
        access = {'grok-subscription': grok_access(args.grok_auth_file)}
    elif args.provider_access_file:
        access = read_json(Path(args.provider_access_file).expanduser())
    elif args.provider_token_env:
        if len(providers) != 1 or providers & (set(LOCAL_SESSION_ENV) | {'openai-chatgpt'}):
            raise OpenRSIError('--provider-token-env requires one API-key provider; use --provider-access-file for ensembles.')
        access = {next(iter(providers)): os.environ.get(args.provider_token_env)}
    else:
        raise OpenRSIError('Select --codex-auth-file, --grok-auth-file, --provider-token-env NAME, or --provider-access-file PATH; '
                            'use --prepare-only to prepare without model access.')
    validate_provider_access(access)
    if set(access) != providers:
        raise OpenRSIError('Credential providers must match exactly the declared models.')
    return access


@contextmanager
def temporary_environment(access):
    """Keep gateway-only access outside retained runs; never copy refresh tokens."""
    # tmpfs when available; otherwise the local OS private temporary directory.
    parent = '/dev/shm' if sys.platform.startswith('linux') and Path('/dev/shm').is_dir() else None
    with tempfile.TemporaryDirectory(prefix='openrsi-local-access-', dir=parent) as directory:
        root = Path(directory)
        root.chmod(0o700)
        environment = {key: os.environ[key] for key in
                       ('PATH', 'HOME', 'TMPDIR', 'USER', 'LOGNAME', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'TERM')
                       if key in os.environ}
        lines = []
        # This is an explicit operator assertion, not a credential or a default.
        # Keep it in the trusted runtime input so Compose can configure the gateway.
        if 'openrouter' in access and os.environ.get('TESTBED_OPENROUTER_INFERENCE_ONLY') == '1':
            lines.append('TESTBED_OPENROUTER_INFERENCE_ONLY=1\n')
        for provider, value in access.items():
            if provider == 'openai-chatgpt':
                path = root / 'auth.json'
                path.touch(mode=0o600)
                path.write_bytes(canonical({'auth_mode': 'chatgpt', 'OPENAI_API_KEY': None,
                    'last_refresh': value['last_refresh'], 'tokens': {
                        key: value[key] for key in ('access_token', 'id_token', 'account_id')}}))
                environment['DUNGENESS_CODEX_AUTH_FILE'] = str(path)
            else:
                lines.extend(f'{key}={item}\n' for key, item in provider_environment(provider, value).items())
        env_file = root / 'runtime.env'
        env_file.touch(mode=0o600)
        env_file.write_text(''.join(lines))
        try:
            yield env_file, environment
        finally:
            access.clear()


def problem_files(selected):
    """Stable local package bytes, also used to recognize older local records."""
    document = {
        'schema_version': 1, 'kind': 'problem', 'id': selected['id'], 'title': selected['title'],
        'slug': selected['slug'], 'release': selected['release'],
        'metric': selected['metric'], 'execution': selected['dungeness'],
    }
    return {'problem.json': (json.dumps(document, indent=2, ensure_ascii=False) + '\n').encode(),
            'instructions.md': problem_statement(selected['id']).encode()}


def prepare(state, package, source, evaluation, *, problem_id='ecdsa.fail', problem_release=None, pricing_path=None):
    from openrsi_space.credentials import require_active_models
    require_active_models(evaluation_models(evaluation))
    selected = get_problem(problem_id, release=problem_release)
    problem_set_digest = digest(initial_problems(release=problem_release))
    source = source.expanduser().resolve()
    if not (source / 'dungeness').is_file():
        raise OpenRSIError('Point --dungeness at a Dungeness checkout (https://github.com/Layr-Labs/dungeness).')
    if git(source, 'status', '--porcelain'):
        raise OpenRSIError('Use a clean Dungeness checkout so the local runtime is reproducible.')
    source_commit = git(source, 'rev-parse', 'HEAD')
    require_problem_service_runtime(source)
    if evaluation['limits'].get('max_model_tokens') is None:
        from openrsi_space.integrations.dungeness.runtime_contract import require_capabilities
        require_capabilities(source, 'optional-model-token-limit-v1')
    pricing = read_json(pricing_path) if pricing_path else pricing_schedule()
    models = evaluation_models(evaluation)
    resolved = []
    for model in models:
        profile = model_profile(source, model['name'], model['provider'], pricing)
        if model.get('reasoning_effort'):
            profile['defaults'] = {'reasoning_effort': model['reasoning_effort']}
        resolved.append(profile)
    package = package.resolve()
    if state.resolve().is_relative_to(package) and state.resolve().relative_to(package).parts[:1] not in (('.openrsi',), (LEGACY_STATE,)):
        raise OpenRSIError('Keep --state outside the harness source directory.')
    print('Building harness source (no model calls during this step)…', file=sys.stderr, flush=True)
    built = executable.build(state, package)
    harness, harness_bytes = snapshot_directory(package, exclude=executable.SOURCE_EXCLUDES)
    if built['source_digest'] != harness['version']:
        raise OpenRSIError('Harness source changed during its build; retry with stable source.')
    run_id = 'local-' + uuid.uuid4().hex[:16]
    folder = state / 'local' / run_id
    folder.mkdir(parents=True)
    (folder / 'harness.zip').write_bytes(harness_bytes)
    extract_bundle(harness_bytes, folder / 'inputs/harness')
    problem_path = folder / 'inputs/problem'
    problem_path.mkdir(parents=True)
    for name, content in problem_files(selected).items():
        (problem_path / name).write_bytes(content)
    problem, problem_bytes = snapshot_directory(problem_path)
    (folder / 'problem.zip').write_bytes(problem_bytes)
    runtime = folder / 'dungeness'
    print('Preparing Dungeness, metered models, and the internal task service…', file=sys.stderr, flush=True)
    # Runs must remain usable after the managed cache or override checkout is removed.
    git(source, 'clone', '--quiet', '--shared', '--dissociate', '--no-checkout', str(source), str(runtime))
    git(runtime, 'checkout', '--quiet', '--detach', source_commit)
    strategy_file = folder / 'inputs/harness/instructions.md'
    assigned = install_task(runtime, problem_path, problem,
                            strategy_file.read_text() if strategy_file.is_file() else '', run_id)
    task_input = {
        'schema_version': 1, 'problem': {k: problem[k] for k in ('id', 'version')},
        'harness': {k: harness[k] for k in ('id', 'version')},
        'candidate_paths': assigned['candidate_paths'], 'problem_service': assigned['problem_service'],
        'model_provider': models[0]['provider'], 'reasoning_effort': models[0].get('reasoning_effort'),
        'budget': {'max_usd': evaluation['max_model_credits'],
                   'max_model_tokens': evaluation['limits'].get('max_model_tokens')},
        'evidence': 'local-development',
    }
    agent, agent_paths = install_agent(runtime, built, resolved[0], task_input)
    write_yaml(runtime / 'services/gateway/pricing.yaml', {
        'schema_version': 1, 'type': 'policy', 'namespace': 'system/dungeness',
        'id': 'model-pricing', 'entries': pricing['entries'],
    })
    # Empty, nonsecret default; the execution command supplies a temporary file.
    env_file = folder / 'no-credentials.env'
    env_file.touch(mode=0o600)
    spec = {
        'schema_version': 1, 'type': 'run-spec', 'namespace': RUNTIME_NAMESPACE, 'id': run_id,
        'task': assigned['task'], 'agent': agent, 'checkpoint': assigned['checkpoint'],
        'budget': task_input['budget'], 'initialization': assigned['initialization'],
        'web_search': {'profile': 'web-search-profile:system/dungeness/disabled-v1'},
        'model_access': {'models': resolved, 'max_parallel_requests': 4,
                         'bounded_requests': True, 'max_output_tokens': 65536,
                         'request_reservation_usd': min(evaluation['max_model_credits'] / 4, 1)},
        'runtime': {'env_file': str(env_file)},
        'labels': {'evidence': 'local-development', PROBLEM_DIGEST_LABEL: problem_set_digest},
    }
    spec_path = runtime / 'run-specs/projects/catalyst' / (run_id + '.yaml')
    write_yaml(spec_path, spec)
    git(runtime, 'add', *assigned['added_paths'], *agent_paths,
        'services/gateway/pricing.yaml', str(spec_path.relative_to(runtime)))
    git(runtime, '-c', 'commit.gpgsign=false', '-c', 'user.name=OpenRSI local',
        '-c', 'user.email=local@localhost', 'commit', '-qm', 'Prepared local research inputs')
    record = runtime / 'runs/projects/catalyst' / run_id / 'record.json'
    metadata = {
        'id': run_id, 'status': 'prepared', 'created_at': now(), 'evidence': 'local-development',
        'official': False, 'dungeness_commit': source_commit,
        'problem_set_digest': problem_set_digest,
        'problem_identity': {'release': selected['release'], 'release_manifest_sha256': problem_set_digest,
                             'assembled_package_sha256': problem['version']},
        'execution_commit': git(runtime, 'rev-parse', 'HEAD'), 'runtime': str(runtime),
        'spec_path': str(spec_path), 'record_path': str(record), 'artifacts': str(folder),
        'evaluation': evaluation, 'build_id': built['id'],
        'problem': task_input['problem'], 'harness': task_input['harness'],
        'initialization': assigned['initialization'],
    }
    write_json(folder / 'run.json', metadata)
    return metadata


def execute_process(command, runtime, environment):
    process = subprocess.Popen(command, cwd=runtime, env=environment, start_new_session=True)
    try:
        while True:
            try:
                return process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                from .diagnostics import document
                run_id = command[command.index('--run-id') + 1]
                path = Path(runtime)/'runs/projects/catalyst'/run_id/'usage/summary.json'
                usage = document(path).get('usage', {})
                count = usage.get('model_requests', 0)
                spend = usage.get('model_cost_usd', usage.get('normalized_usd'))
                print(f'Local run: {count if type(count) is int else 0} model requests; '
                      f'usage USD equivalent: {spend if type(spend) in (int, float) else "pending"}. '
                      f'Live accounting: {path}', file=sys.stderr, flush=True)
    except KeyboardInterrupt:
        # Let Dungeness stop its containers before temporary access disappears.
        for sig, timeout in ((signal.SIGINT, 60), (signal.SIGTERM, 15), (signal.SIGKILL, 5)):
            if process.poll() is not None:
                break
            os.killpg(process.pid, sig)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                continue
        raise


def run(args, state):
    from openrsi_space.client.configuration import evaluation_config
    overrides = {key: getattr(args, key) for key in
                 ('provider', 'model', 'reasoning_effort', 'budget', 'max_tokens', 'max_seconds')
                 if getattr(args, key) is not None}
    if getattr(args, 'no_token_limit', False):
        overrides['max_tokens'] = None
    evaluation = evaluation_config(Path(args.package) / 'evaluation.json', overrides, check_pricing=False)
    from openrsi_space.credentials import require_active_models
    require_active_models(evaluation_models(evaluation))
    validate_credential_locations(args)
    if not getattr(args, 'local_only', False):
        from openrsi_space.client.model_preflight import check
        prices = read_json(Path(args.pricing)) if args.pricing else pricing_schedule()
        remote_models = check(evaluation_models(evaluation), prices)
        print('Remote model pairing checked: ' + ', '.join(m['name'] for m in remote_models) +
              '. Source, problem, reasoning, evidence and allowance checks still apply at submission.',
              file=sys.stderr, flush=True)
    else:
        print('Local-only experiment: remote model eligibility was not checked.', file=sys.stderr, flush=True)
    from openrsi_space.integrations.dungeness.managed_runtime import resolve
    runtime_source = resolve(args.dungeness)
    access = None
    if not args.prepare_only:
        if not all(shutil.which(name) for name in ('docker', 'git', 'uv', 'uvx')):
            raise OpenRSIError('Install Git, Docker, and uv (including uvx) before a full local run.')
        access = credential_input(args, {m['provider'] for m in evaluation_models(evaluation)})
        print(f"LOCAL MODEL ACCESS: This run uses YOUR model account on this machine, with a "
              f"{evaluation['max_model_credits']:g} normalized-credit cap. Calls consume your API credits "
              'or subscription allowance; an in-flight response can exceed the cap. '
              'No credentials are sent to OpenRSI or Yukon.', file=sys.stderr, flush=True)
    try:
        metadata = prepare(state, Path(args.package), runtime_source, evaluation,
                           problem_id=args.problem, problem_release=args.problem_release,
                           pricing_path=Path(args.pricing) if args.pricing else None)
        if args.prepare_only:
            print(json.dumps(metadata, indent=2))
            return 0
        metadata['status'] = 'running'
        output = Path(metadata['artifacts']) / 'run.json'
        write_json(output, metadata)
        try:
            executable.inspect_build(state, metadata['build_id'])
            with temporary_environment(access) as (env_file, environment):
                command = [sys.executable, str(Path(metadata['runtime']) / 'dungeness'), 'run',
                           metadata['spec_path'], '--namespace', RUNTIME_NAMESPACE, '--run-id', metadata['id'],
                           '--env-file', str(env_file), '--keep-render', '--keep-images',
                           '--agent-timeout-sec', str(evaluation['limits']['max_seconds'])]
                code = execute_process(command, metadata['runtime'], environment)
            metadata.update(status='completed' if code == 0 else 'failed', exit_code=code,
                            runtime_exit_code=code)
        except KeyboardInterrupt:
            metadata['status'] = 'cancelled'
            code = 130
        except BaseException:
            metadata['status'] = 'failed'
            raise
        finally:
            metadata['finished_at'] = now()
            write_json(output, metadata)
        record = Path(metadata['record_path'])
        if record.is_file():
            from .diagnostics import summarize
            diagnostic = summarize(record)
            record_status = diagnostic.pop('record_status')
            metadata.update(diagnostic)
            if code == 0 and record_status != 'completed':
                metadata.update(status='failed', exit_code=1)
                code = 1
        elif code == 0:
            metadata.update(status='failed', exit_code=1, local_evidence_precheck_passed=False,
                            diagnostics=[{'code': 'missing_run_record', 'message': 'Dungeness did not retain a run record.'}])
            code = 1
        write_json(output, metadata)
        print(json.dumps(metadata, indent=2))
        return code
    finally:
        if access is not None:
            access.clear()
