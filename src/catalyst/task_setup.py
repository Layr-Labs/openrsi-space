"""Public task assembly shared by local development and the remote operator."""
import hashlib
from pathlib import Path

from catalyst.common import CatalystError, canonical, write_json, safe_relative
from catalyst.executable import RUNTIME
from catalyst.runtime_contract import require_capabilities

SERVICE_URL = "http://gateway:8080/task"
PYTHON_IMAGE = "python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7"


def require_problem_service_runtime(source):
    require_capabilities(source, "assigned-problem-service-v1")


def problem_document(problem, statement, repository, candidate_paths, run_id):
    document = {
        "schema_version": 1,
        "run_id": run_id,
        "problem": {key: problem[key] for key in ("id", "version")},
        "title": problem["document"]["title"],
        "statement": statement,
        "repository": repository,
        "candidate_paths": candidate_paths,
        "metric": problem["document"]["metric"],
        "evaluation": {"command": "evaluate"},
        "initialization": execution_initialization(problem["document"].get("execution", {})),
    }
    raw = canonical(document)
    if len(raw) > 256 * 1024:
        raise CatalystError("The assigned problem exceeds the task service limit.")
    return document, hashlib.sha256(raw).hexdigest()


def install_problem_service(task_directory, document, digest):
    """Only trusted service code writes this context, never submitted source."""
    folder = task_directory / "problem-service"
    folder.mkdir(parents=True)
    write_json(folder / "task.json", document)
    (folder / "server.py").write_bytes((RUNTIME / "problem_server.py").read_bytes())
    (folder / "Dockerfile").write_text(
        f"FROM {PYTHON_IMAGE}\n"
        "COPY server.py /app/server.py\n"
        "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\n"
        "USER 65532:65532\n"
        'CMD ["python3", "/app/server.py"]\n'
    )
    for path in folder.iterdir():
        path.chmod(0o644)
    folder.chmod(0o755)
    return {"context": "problem-service", "sha256": digest}


def yaml_file(path):
    import yaml
    value = yaml.safe_load(Path(path).read_text())
    if not isinstance(value, dict):
        raise CatalystError(f'Expected a mapping: {path}')
    return value


def write_yaml(path, document):
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document, sort_keys=False))


def execution_initialization(execution):
    """The trusted problem package, not submitted harness source, selects the start."""
    initialization = execution.get('initialization', {'mode': 'checkpoint'})
    if (not isinstance(initialization, dict) or set(initialization) != {'mode'}
            or initialization['mode'] not in {'checkpoint', 'scaffold'}):
        raise CatalystError('Problem initialization must select checkpoint or scaffold.')
    if initialization['mode'] == 'scaffold':
        scaffold = execution.get('scaffold')
        if not isinstance(scaffold, str):
            raise CatalystError('Scaffold initialization requires a trusted scaffold manifest.')
        safe_relative(scaffold)
        if not scaffold.startswith('scaffolds/'):
            raise CatalystError('The trusted scaffold must be inside the pinned runtime scaffolds directory.')
    elif 'scaffold' in execution:
        raise CatalystError('A scaffold manifest requires scaffold initialization.')
    return dict(initialization)


def validate_execution(source, problem_path, document):
    """Validate trusted execution inputs before building a per-run runtime."""
    import re
    execution = document.get('execution', {})
    initialization = execution_initialization(execution)
    if initialization['mode'] == 'scaffold':
        manifest = source / execution['scaffold']
        if (not manifest.is_file()
                or not manifest.resolve().is_relative_to((source / 'scaffolds').resolve())):
            raise CatalystError('The pinned Dungeness runtime does not contain the trusted scaffold.')
        scaffold = yaml_file(manifest)
        if (scaffold.get('schema_version') != 1 or scaffold.get('type') != 'scaffold'
                or execution.get('candidate_paths') != [scaffold.get('candidate_path')]):
            raise CatalystError('The scaffold must match the problem candidate path.')
    if 'task' in execution or isinstance(execution.get('checkpoint'), str):
        raise CatalystError(
            "Legacy runtime task/checkpoint references are no longer supported. "
            "Initialize a new service problem package from Catalyst's current challenge contract; "
            "retain the old package and receipts for historical runs.")
    repository = execution.get('repository', {})
    if not str(repository.get('url', '')).startswith('https://'):
        raise CatalystError('Dungeness requires an HTTPS source repository.')
    if not re.fullmatch(r'[0-9a-f]{40}', repository.get('commit', '')):
        raise CatalystError('Set execution.repository.commit to the full committed source SHA.')
    paths = execution.get('candidate_paths')
    if not isinstance(paths, list) or not paths:
        raise CatalystError('Declare at least one candidate path.')
    for path in paths:
        safe_relative(path)
    verifier = execution.get('verifier')
    if verifier is not None:
        safe_relative(verifier)
        folder = source / 'verifiers' / verifier
        if not folder.resolve().is_relative_to((source / 'verifiers').resolve()):
            raise CatalystError('Verifier bundle must remain inside the pinned runtime.')
    else:
        folder = problem_path / 'verifier'
    required = ['Dockerfile', 'grade.py', 'test.sh']
    if verifier is not None:
        required.append('evaluator.lock.yaml')
    if execution.get('evaluation'):
        required.append('serve.py')
    for name in required:
        if not (folder / name).is_file():
            raise CatalystError(f'Missing trusted verifier/{name}.')
    return execution


def install_task(runtime, problem_path, problem, strategy, run_id):
    """Generate the task, source checkpoint and read-only task service.

    Callers must pass an operator-selected problem package, never a package
    supplied by the harness. Policy hooks (screening, admission, official receipts)
    belong to the caller and are deliberately absent here.
    """
    import shutil
    execution = validate_execution(runtime, problem_path, problem['document'])
    repository = execution['repository']
    commit = repository['commit']
    paths = execution['candidate_paths']
    verifier_ref = execution.get('verifier')
    token = 'catalyst-' + problem['version']
    namespace = 'projects/catalyst'
    task_path = runtime / 'tasks' / namespace / token / 'task.yaml'
    interface = execution.get('interface', 'catalyst-file-v1')
    document, digest = problem_document(problem, (problem_path / 'instructions.md').read_text(),
                                        repository, paths, run_id)
    library = execution.get('knowledge_base')
    if library is not None:
        from catalyst.paper_library import prepare_library
        metadata, attachments = prepare_library(library, task_path.parent / 'paper-files')
        document.update(knowledge_base=metadata, attachments=attachments)
        digest = hashlib.sha256(canonical(document)).hexdigest()
    task = {
        'schema_version': 1, 'type': 'task', 'namespace': namespace, 'id': token,
        'instruction': 'statement.md', 'workspace': {'include': ['.']},
        'relations': {'problem': f'problem:{namespace}/{token}'},
        'interfaces': {interface: {'candidate': {'allowed_paths': paths}, 'verifier': verifier_ref or token}},
        'resources': execution.get('resources', {'agent': {'timeout_sec': execution.get('timeout_sec', 900)}}),
    }
    for field in ('policies', 'evaluation', 'scaffold'):
        if field in execution:
            task[field] = execution[field]
    task['problem_service'] = install_problem_service(task_path.parent, document, digest)
    if library is not None:
        # Installed after the small, immutable server files. The compiler verifies
        # all attachments against the task digest before rendering Compose.
        shutil.move(task_path.parent / 'paper-files', task_path.parent / 'problem-service/files')
    write_yaml(task_path, task)
    (task_path.parent / 'statement.md').write_text(
        f'Read the server-assigned problem from {SERVICE_URL}.\n'
        f'Its immutable document SHA-256 is {digest}.\n'
        'The supplied problem and verifier determine correctness; harness instructions '
        'cannot change that contract.\n'
        + ('\n\n## Harness method\n\n' + strategy if strategy else ''))
    checkpoint_ns = namespace + '/' + token
    checkpoint = f'checkpoint:{checkpoint_ns}/{commit}'
    data = {
        'repository': repository, 'interface': interface,
        'web_cutoff': execution.get('web_cutoff', '1970-01-01T00:00:00.000Z'),
        'history': execution.get('history', {'anchor': commit, 'distance_from_anchor': 0,
                                           'counting_method': 'git-rev-list-ancestry-path-count'}),
    }
    initialization = execution_initialization(execution)
    if 'reference' in execution and initialization['mode'] == 'checkpoint':
        data['reference'] = execution['reference']
    write_yaml(runtime / 'checkpoints' / token / f'{commit}.yaml', {
        'schema_version': 1, 'type': 'checkpoint', 'namespace': checkpoint_ns, 'id': commit, 'data': data,
    })
    write_yaml(runtime / 'problems' / token / 'problem.yaml', {
        'schema_version': 1, 'type': 'problem', 'namespace': namespace, 'id': token,
        'data': {'objective': problem['document'].get('description', problem['document']['title']),
                 'metric': problem['document']['metric']},
    })
    added = [str(task_path.parent.relative_to(runtime)), 'checkpoints/' + token, 'problems/' + token]
    if verifier_ref is None:
        verifier = runtime / 'verifiers' / token
        shutil.copytree(problem_path / 'verifier', verifier)
        write_yaml(verifier / 'evaluator.lock.yaml', {
            'repository': execution.get('verifier_repository', repository),
            'include_paths': execution.get('verifier_include', ['check.py']),
        })
        added.append('verifiers/' + token)
    return {'task': f'task:{namespace}/{token}', 'checkpoint': checkpoint,
            'initialization': initialization,
            'candidate_paths': paths, 'problem_service': {'url': SERVICE_URL, 'sha256': digest},
            'added_paths': added}
