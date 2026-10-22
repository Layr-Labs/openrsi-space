"""Public local Dungeness runs: no hosted API, Yukon login, or official receipts."""
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

from .common import CatalystError, canonical, extract_bundle, now, read_json, snapshot_directory, write_json
from . import executable
from .agent_setup import install_agent, model_profile
from .problems import get_problem, problem_statement
from .task_setup import install_task, require_problem_service_runtime, write_yaml
from .tiers import evaluation_models, pricing_schedule
from .provider_profiles import PROFILES

PROVIDER_ENV = {
    'openai': 'TESTBED_OPENAI_API_KEY', 'anthropic': 'TESTBED_ANTHROPIC_API_KEY',
    'openrouter': 'TESTBED_OPENROUTER_API_KEY', 'moonshot': 'TESTBED_MOONSHOT_API_KEY',
    'kimi-code': 'TESTBED_KIMI_CODE_API_KEY',
    **{name: 'TESTBED_' + profile['credential_env'] for name, profile in PROFILES.items()},
}


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
    if result.returncode:
        raise CatalystError(result.stderr.strip() or 'Git command failed.')
    return result.stdout.strip()


def validate_credential_locations(args):
    package = Path(args.package).resolve()
    for name in ('codex_auth_file', 'provider_access_file', 'grok_auth_file'):
        path = getattr(args, name, None)
        if path and Path(path).expanduser().resolve().is_relative_to(package):
            raise CatalystError('Keep model credential files outside the harness source directory.')


def credential_input(args, providers):
    from .credentials import decode_codex_access, encode_codex_access, validate_provider_access
    validate_credential_locations(args)
    if getattr(args, 'grok_auth_file', None):
        from .credentials import grok_access
        access = {'grok-subscription': grok_access(args.grok_auth_file)}
    elif args.codex_auth_file:
        access = {'openai-chatgpt': decode_codex_access(encode_codex_access(args.codex_auth_file))}
    elif args.provider_access_file:
        access = read_json(Path(args.provider_access_file).expanduser())
    elif args.provider_token_env:
        if len(providers) != 1 or 'openai-chatgpt' in providers:
            raise CatalystError('--provider-token-env requires one API-key provider; use --provider-access-file for ensembles.')
        access = {next(iter(providers)): os.environ.get(args.provider_token_env)}
    else:
        raise CatalystError('Select --grok-auth-file, --codex-auth-file, --provider-token-env NAME, or --provider-access-file PATH; '
                            'use --prepare-only to prepare without model access.')
    validate_provider_access(access)
    if set(access) != providers:
        raise CatalystError('Credential providers must match exactly the declared models.')
    return access


@contextmanager
def temporary_environment(access):
    """Keep gateway-only access outside retained runs; never copy refresh tokens."""
    # tmpfs when available; otherwise the local OS private temporary directory.
    parent = '/dev/shm' if sys.platform.startswith('linux') and Path('/dev/shm').is_dir() else None
    with tempfile.TemporaryDirectory(prefix='catalyst-local-access-', dir=parent) as directory:
        root = Path(directory)
        root.chmod(0o700)
        environment = {key: os.environ[key] for key in
                       ('PATH', 'HOME', 'TMPDIR', 'USER', 'LOGNAME', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'TERM')
                       if key in os.environ}
        lines = []
        for provider, value in access.items():
            if provider == 'openai-chatgpt':
                path = root / 'auth.json'
                path.touch(mode=0o600)
                path.write_bytes(canonical({'auth_mode': 'chatgpt', 'OPENAI_API_KEY': None,
                    'last_refresh': value['last_refresh'], 'tokens': {
                        key: value[key] for key in ('access_token', 'id_token', 'account_id')}}))
                environment['DUNGENESS_CODEX_AUTH_FILE'] = str(path)
            else:
                if PROFILES.get(provider, {}).get('credential_kind') == 'session-token':
                    lines.append(f"{PROVIDER_ENV[provider]}_EXPIRES_AT={value['expires_at']}\n")
                    value = value['access_token']
                lines.append(f'{PROVIDER_ENV[provider]}={value}\n')
        env_file = root / 'runtime.env'
        env_file.touch(mode=0o600)
        env_file.write_text(''.join(lines))
        try:
            yield env_file, environment
        finally:
            access.clear()


def prepare(state, package, source, evaluation, *, problem_id='ecdsa.fail', pricing_path=None):
    source = source.expanduser().resolve()
    if not (source / 'dungeness').is_file():
        raise CatalystError('Point --dungeness at a Dungeness checkout (https://github.com/Layr-Labs/dungeness).')
    if git(source, 'status', '--porcelain'):
        raise CatalystError('Use a clean Dungeness checkout so the local runtime is reproducible.')
    source_commit = git(source, 'rev-parse', 'HEAD')
    require_problem_service_runtime(source)
    if evaluation['limits'].get('max_model_tokens') is None:
        from .runtime_contract import require_capabilities
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
    if state.resolve().is_relative_to(package) and state.resolve().relative_to(package).parts[:1] != ('.catalyst',):
        raise CatalystError('Keep --state outside the harness source directory.')
    print('Building harness source (no model calls during this step)…', file=sys.stderr, flush=True)
    built = executable.build(state, package)
    harness, harness_bytes = snapshot_directory(package, exclude=executable.SOURCE_EXCLUDES)
    if built['source_digest'] != harness['version']:
        raise CatalystError('Harness source changed during its build; retry with stable source.')
    run_id = 'local-' + uuid.uuid4().hex[:16]
    folder = state / 'local' / run_id
    folder.mkdir(parents=True)
    (folder / 'harness.zip').write_bytes(harness_bytes)
    extract_bundle(harness_bytes, folder / 'inputs/harness')
    selected = get_problem(problem_id)
    problem_path = folder / 'inputs/problem'
    write_json(problem_path / 'problem.json', {
        'schema_version': 1, 'kind': 'problem', 'id': selected['id'], 'title': selected['title'],
        'metric': selected['metric'], 'execution': selected['dungeness'],
    })
    (problem_path / 'instructions.md').write_text(problem_statement(problem_id))
    problem, problem_bytes = snapshot_directory(problem_path)
    (folder / 'problem.zip').write_bytes(problem_bytes)
    runtime = folder / 'dungeness'
    print('Preparing Dungeness, metered models, and the internal task service…', file=sys.stderr, flush=True)
    git(source, 'clone', '--quiet', '--shared', '--no-checkout', str(source), str(runtime))
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
        'schema_version': 1, 'type': 'run-spec', 'namespace': 'projects/catalyst', 'id': run_id,
        'task': assigned['task'], 'agent': agent, 'checkpoint': assigned['checkpoint'],
        'budget': task_input['budget'], 'initialization': assigned['initialization'],
        'web_search': {'profile': 'web-search-profile:system/dungeness/disabled-v1'},
        'model_access': {'models': resolved, 'max_parallel_requests': 4,
                         'request_reservation_usd': min(evaluation['max_model_credits'] / 4, 1)},
        'runtime': {'env_file': str(env_file)},
        'labels': {'evidence': 'local-development'},
    }
    spec_path = runtime / 'run-specs/projects/catalyst' / (run_id + '.yaml')
    write_yaml(spec_path, spec)
    git(runtime, 'add', *assigned['added_paths'], *agent_paths,
        'services/gateway/pricing.yaml', str(spec_path.relative_to(runtime)))
    git(runtime, '-c', 'commit.gpgsign=false', '-c', 'user.name=Catalyst local',
        '-c', 'user.email=local@localhost', 'commit', '-qm', 'Prepared local research inputs')
    record = runtime / 'runs/projects/catalyst' / run_id / 'record.json'
    metadata = {
        'id': run_id, 'status': 'prepared', 'created_at': now(), 'evidence': 'local-development',
        'official': False, 'dungeness_commit': source_commit,
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
        return process.wait()
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
    from .remote import evaluation_config
    overrides = {key: getattr(args, key) for key in
                 ('provider', 'model', 'reasoning_effort', 'budget', 'max_tokens', 'max_seconds')
                 if getattr(args, key) is not None}
    if getattr(args, 'no_token_limit', False):
        overrides['max_tokens'] = None
    evaluation = evaluation_config(Path(args.package) / 'evaluation.json', overrides, check_pricing=False)
    validate_credential_locations(args)
    access = None
    if not args.prepare_only:
        if not all(shutil.which(name) for name in ('docker', 'git', 'uv', 'uvx')):
            raise CatalystError('Install Git, Docker, and uv (including uvx) before a full local run.')
        access = credential_input(args, {m['provider'] for m in evaluation_models(evaluation)})
        print(f"LOCAL MODEL ACCESS: This run uses YOUR model account on this machine, with a "
              f"{evaluation['max_model_credits']:g} normalized-credit cap. Calls consume your API credits "
              'or subscription allowance; an in-flight response can exceed the cap. '
              'No credentials are sent to Catalyst or Yukon.', file=sys.stderr, flush=True)
    try:
        metadata = prepare(state, Path(args.package), Path(args.dungeness), evaluation,
                           problem_id=args.problem, pricing_path=Path(args.pricing) if args.pricing else None)
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
                           metadata['spec_path'], '--namespace', 'projects/catalyst', '--run-id', metadata['id'],
                           '--env-file', str(env_file), '--keep-render', '--keep-images',
                           '--agent-timeout-sec', str(evaluation['limits']['max_seconds'])]
                code = execute_process(command, metadata['runtime'], environment)
            metadata.update(status='completed' if code == 0 else 'failed', exit_code=code)
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
            data = read_json(record).get('data', {})
            metadata['usage'] = data.get('usage', {})
            metadata['metrics'] = data.get('metrics', {})
            write_json(output, metadata)
        print(json.dumps(metadata, indent=2))
        return code
    finally:
        if access is not None:
            access.clear()
