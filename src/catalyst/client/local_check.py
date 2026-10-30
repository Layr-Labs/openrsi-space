"""A local CLI readiness check, not trusted remote evidence or anti-cheat policy."""
import json
from pathlib import Path
import shlex

from catalyst.common import CatalystError, digest_files, read_json
from catalyst.contracts.accounting import evaluation_models
from catalyst.contracts.results import digest
from catalyst.contracts.model_equivalence import model_binding


def request_identity(body):
    # Prices may be quoted later. Limits are included here for retry identity,
    # but are deliberately not compared with the local test's limits.
    return digest({key: body[key] for key in
                   ('source', 'evaluation', 'problem_set', 'publication', 'evidence_mode', 'judge', 'context')})


def _models(models, *, runtime=False):
    return model_binding(record_models(models) if runtime else models)


def record_models(models):
    return [{'provider': m['provider'], 'name': m['request_model'],
             **({'reasoning_effort': m['defaults']['reasoning_effort']}
                if m.get('defaults', {}).get('reasoning_effort') else {})} for m in models]


def _record(path):
    path = path.expanduser().resolve()
    if path.is_dir():
        path = path / ('run.json' if (path / 'run.json').is_file() else 'record.json')
    document = read_json(path)
    if 'record_path' in document:
        if document.get('status') != 'completed' or document.get('exit_code') != 0:
            raise ValueError('the local run did not complete')
        # Prefer the adjacent artifact tree so moved run folders still work.
        adjacent = path.parent / 'dungeness/runs/projects/catalyst' / document['id'] / 'record.json'
        path = adjacent if adjacent.is_file() else Path(document['record_path'])
        document = read_json(path)
    return path, document


def validate_record(path, body):
    path, record = _record(path)
    data = record['data']
    if record.get('labels', {}).get('evidence') != 'local-development' or data['status'] != 'completed':
        raise ValueError('a completed local-development run is required')
    stats = data['execution']['stats']
    if stats.get('n_completed_trials', 0) < 1 or stats.get('n_errored_trials') != 0:
        raise ValueError('the runtime reported an execution error')
    agent = data['configuration']['sources']['agent']['document']
    if agent.get('execution', {}).get('interface') != 'dungeness-command-v1':
        raise ValueError('the run did not use the supported command harness interface')
    package = data['agent']['package']
    if package.get('name') != 'catalyst-exec-v1' or package.get('version') != body['source']['digest']:
        raise ValueError('the harness source changed')
    problem_digest = record['labels'].get('catalyst_problem_set_digest')
    if problem_digest is None:
        # Existing local runs predate the explicit official identity label.
        from catalyst.integrations.dungeness.local import problem_files
        expected = 'catalyst-' + digest_files(problem_files(body['problem_set'][0]))
        if len(body['problem_set']) != 1 or data['problem']['id'] != expected:
            raise ValueError('the problem package differs or cannot be identified')
    elif problem_digest != digest(body['problem_set']):
        raise ValueError('the assigned problem changed')
    models = agent.get('model_access', {}).get('models') or [data['model']]
    if _models(models, runtime=True) != _models(evaluation_models(body['evaluation'])):
        raise ValueError('the model or reasoning settings differ, or the provider pair has no supported equivalence')
    usage = data['usage']
    if usage.get('model_accounting_state') != 'settled' or usage.get('model_requests', 0) < 1:
        raise ValueError('model usage is missing or unsettled')
    successful = set()
    with (path.parent / 'usage/events.jsonl').open() as events:
        for line in events:
            event = json.loads(line)
            item = event.get('data', {})
            if (event.get('run_id') == data['run_id'] and event.get('kind') == 'model.accounting'
                    and item.get('status') == 'success' and item.get('accounting_method') == 'gateway'
                    and item.get('total_tokens', 0) > 0):
                successful.add((item.get('provider'), item.get('model')))
    required = {(m['provider'], m['request_model']) for m in models}
    if not required <= successful:
        raise ValueError('not every declared model has a successful accounted response')
    return {'status': 'passed', 'run_id': data['run_id'], 'record_path': str(path),
            'models': record_models(models)}


def check_submission(state, package, body, base, *, local_run=None):
    identity = request_identity(body)
    decision = {'request_identity': identity}
    # Existing operation keys must remain usable even if local logs were moved
    # or removed. This resumes the same request, never creates an exemption for
    # changed source, model, limits, problem, publication choices or endpoint.
    if local_run is None:
        for folder in (state / 'remote/pending', state / 'yukon/pending'):
            for path in folder.glob('*.json'):
                try:
                    saved = read_json(path)
                    body_without_id = {k: v for k, v in saved.items() if k != 'request_id'}
                    expected_name = digest({'base': base, 'body': body_without_id}) + '.json'
                    if (saved.get('request_id') and path.name == expected_name
                            and request_identity(saved) == identity):
                        return {**decision, 'status': 'resuming', 'request_id': saved['request_id'],
                                **({'local_evidence': saved['local_evidence']} if 'local_evidence' in saved else {})}
                except (OSError, ValueError, KeyError, TypeError, CatalystError):
                    continue
    paths = [local_run] if local_run is not None else sorted({
        path for root in (state, package.resolve() / '.catalyst')
        for path in (root / 'local').glob('*/run.json')
    }, reverse=True)
    reason = 'no matching completed local run was found'
    for path in paths:
        try:
            return {**decision, **validate_record(path, body)}
        except (OSError, ValueError, KeyError, TypeError, AttributeError, CatalystError) as error:
            if local_run is not None:
                reason = str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else 'the selected local record is missing or incomplete'
    raise CatalystError(
        f'Local Dungeness check required: {reason}. Run openrsi-space local run '
        f'{shlex.quote(str(package))} --dungeness /path/to/dungeness with the same model and problem '
        'and an authorized local budget. Existing records are reused automatically under '
        f'{state / "local"}; use --local-run PATH for another location. '
        'A completed matching local run is required; the check cannot be skipped. '
        'A valid circuit is not required. No remote evaluation was submitted.')
