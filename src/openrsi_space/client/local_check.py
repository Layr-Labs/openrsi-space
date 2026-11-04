"""A local CLI readiness check, not trusted remote evidence or anti-cheat policy."""
from openrsi_space.compatibility import LEGACY_STATE, PROBLEM_DIGEST_LABEL, PROBLEM_PREFIX
import json
from pathlib import Path
import shlex

from openrsi_space.contracts.harness import INTERFACES
from openrsi_space.common import OpenRSIError, digest_files, read_json, canonical
from openrsi_space.contracts.accounting import evaluation_models, credit_limit
from openrsi_space.contracts.results import digest
from openrsi_space.contracts.model_equivalence import model_binding
from openrsi_space.contracts.local_evidence import validate_exchanges, TERMINAL_STATUSES, KINDS


def request_identity(body):
    # Prices may be quoted later. Limits remain part of retry identity.
    return digest({key: body[key] for key in
                   ('source', 'evaluation', 'problem_set', 'publication', 'evidence_mode', 'judge', 'context')})


def _models(models, *, runtime=False):
    return model_binding(record_models(models) if runtime else models)


def record_models(models):
    return [{'provider': m['provider'], 'name': m['request_model'],
             **({'reasoning_effort': m['defaults']['reasoning_effort']}
                if m.get('defaults', {}).get('reasoning_effort') else {})} for m in models]


def _record(path, *, with_metadata=False):
    path = path.expanduser().resolve()
    if path.is_dir():
        path = path / ('run.json' if (path / 'run.json').is_file() else 'record.json')
    document = read_json(path)
    metadata = None
    if 'record_path' in document:
        if document.get('status') not in TERMINAL_STATUSES:
            raise ValueError('the local run has not ended')
        metadata = document
        # Prefer the adjacent artifact tree so moved run folders still work.
        adjacent = path.parent / 'dungeness/runs/projects/catalyst' / document['id'] / 'record.json'
        path = adjacent if adjacent.is_file() else Path(document['record_path'])
        document = read_json(path)
    if metadata is not None and metadata.get('id') != document.get('data', {}).get('run_id'):
        raise ValueError('the local metadata identifies a different run')
    return (path, document, metadata) if with_metadata else (path, document)



def recorded_events(path, run_id):
    events, size = [], 0
    # The export and server have the same finite envelope limits.
    maximum = 192 * 1024 * 1024
    with (path.parent / 'usage/events.jsonl').open('rb') as stream:
        while line := stream.readline(maximum + 1):
            if len(line) > maximum:
                raise OpenRSIError('Local evidence exceeds 192 MiB; use a shorter readiness run.')
            event = json.loads(line)
            if not isinstance(event, dict):
                raise OpenRSIError('A retained local event is malformed.')
            if event.get('run_id') != run_id or event.get('kind') not in KINDS:
                continue
            item = {key: event.get(key) for key in ('kind', 'request_id', 'sequence', 'data')}
            size += len(canonical(item))
            if size > maximum:
                raise OpenRSIError('Local evidence exceeds 192 MiB; use a shorter readiness run.')
            events.append(item)
            if len(events) > 6000:
                raise OpenRSIError('Local evidence exceeds 6000 events; use a shorter readiness run.')
    return events


def check_recorded_calls(path, data, models):
    usage = data['usage']
    if type(usage.get('model_requests')) is not int or usage['model_requests'] < 1:
        raise ValueError('no model requests were accounted; inspect the local diagnostics')
    if usage.get('model_accounting_state') != 'settled':
        raise ValueError('model accounting is incomplete; unknown usage is not zero')
    calls = validate_exchanges(recorded_events(path, data['run_id']), models)
    if len(calls) != usage['model_requests']:
        raise ValueError('retained exchanges do not match the recorded model-request count')
    return calls

def validate_record(path, body):
    selected_path = str(path.expanduser().resolve())
    path, record, metadata = _record(path, with_metadata=True)
    data = record['data']
    if record.get('labels', {}).get('evidence') != 'local-development' or data['status'] not in TERMINAL_STATUSES:
        raise ValueError('an ended local-development run is required')
    stats = data['execution']['stats']
    if (not any(type(stats.get(k)) is int and stats[k] > 0 for k in
                    ('n_completed_trials', 'n_errored_trials', 'n_cancelled_trials'))
            or stats.get('n_running_trials', 0) != 0
            or stats.get('n_pending_trials', 0) != 0):
        raise ValueError('the runtime has not finished its local trial')
    agent = data['configuration']['sources']['agent']['document']
    if agent.get('execution', {}).get('interface') != 'dungeness-command-v1':
        raise ValueError('the run did not use the supported command harness interface')
    package = data['agent']['package']
    if package.get('name') not in INTERFACES or package.get('version') != body['source']['digest']:
        raise ValueError('the harness source changed')
    problem_digest = record['labels'].get(PROBLEM_DIGEST_LABEL)
    if problem_digest is None:
        # Existing local runs predate the explicit official identity label.
        from openrsi_space.integrations.dungeness.local import problem_files
        expected = PROBLEM_PREFIX + digest_files(problem_files(body['problem_set'][0]))
        if len(body['problem_set']) != 1 or data['problem']['id'] != expected:
            raise ValueError('the problem package differs or cannot be identified')
    elif problem_digest != digest(body['problem_set']):
        raise ValueError('the assigned problem changed')
    models = agent.get('model_access', {}).get('models') or [data['model']]
    if _models(models, runtime=True) != _models(evaluation_models(body['evaluation'])):
        raise ValueError('the model or reasoning settings differ, or the provider pair has no supported equivalence')
    # Use the effective configuration retained by Dungeness, never the new
    # remote request or the current (possibly edited) harness evaluation.json.
    cap = data['configuration'].get('resolved', {}).get('limits', {}).get('max_usd')
    try:
        local_cap = credit_limit(cap)
    except OpenRSIError:
        raise ValueError('the local record lacks a valid positive finite budget cap; '
                         'select an original Dungeness record containing its recorded cap') from None
    if local_cap < credit_limit(body['evaluation']['max_model_credits']):
        raise ValueError(f'the recorded local budget cap (${local_cap}) is below the requested '
                         f"remote budget (${body['evaluation']['max_model_credits']}); lower the remote "
                         'budget or select a matching local run with a sufficient cap; '
                         'actual local spending may be lower')
    check_recorded_calls(path, data, record_models(models))
    # Preserve failure/cancellation even when an outer wrapper and trial differ.
    statuses = {data['status'], metadata.get('status') if metadata else None}
    run_status = next(status for status in ('failed', 'cancelled', 'completed') if status in statuses)
    return {'status': 'passed', 'run_id': data['run_id'], 'record_path': str(path),
            'models': record_models(models), 'local_budget_cap_usd': cap,
            'local_run_path': selected_path, 'local_run_status': run_status}


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
                except (OSError, ValueError, KeyError, TypeError, OpenRSIError):
                    continue
    paths = [local_run] if local_run is not None else sorted({
        path for root in (state, package.resolve() / '.openrsi', package.resolve() / LEGACY_STATE)
        for path in (root / 'local').glob('*/run.json')
    }, reverse=True)
    reason = 'no matching ended local run with complete evidence was found'
    for path in paths:
        try:
            return {**decision, **validate_record(path, body)}
        except (OSError, ValueError, KeyError, TypeError, AttributeError, OpenRSIError) as error:
            if local_run is not None:
                reason = str(error) if isinstance(error, ValueError) and not isinstance(error, json.JSONDecodeError) else 'the selected local record is missing or incomplete'
    raise OpenRSIError(
        f'Local Dungeness check required: {reason}. Run openrsi-space local run '
        f'{shlex.quote(str(package))} --dungeness /path/to/dungeness with the same model and problem '
        'and an authorized local budget. Existing records are reused automatically under '
        f'{state / "local"}; use --local-run PATH for another location. '
        'An ended matching local run with complete exchanges and settled accounting is required; the check cannot be skipped. '
        'A valid circuit is not required. No remote evaluation was submitted.')
