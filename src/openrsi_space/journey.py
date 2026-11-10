"""Read-only journey observations and a portable chat/terminal status card."""
import json
from pathlib import Path
import textwrap

from openrsi_space.common import OpenRSIError
from openrsi_space.contracts.results import TERMINAL, bound_result
from openrsi_space.progress import number

PHASES = (
    ('choose', 'Choose an idea'), ('prepare', 'Prepare the harness'),
    ('local', 'Test locally'), ('readiness', 'Review readiness'),
    ('remote', 'Verify remotely'), ('results', 'Explore results'),
)


def read(path, limit=2 * 1024 * 1024):
    with Path(path).open('rb') as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError('Record too large')
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError('Expected an object')
    return value


def mapping(value):
    return value if isinstance(value, dict) else {}


def enum(value, allowed):
    return value if isinstance(value, str) and value in allowed else 'unknown'


def base():
    return {'schema_version': 1, 'phase': 'choose', 'availability': 'no_records',
            'source': 'workspace', 'execution': 'unknown', 'verification': 'unknown',
            'evidence_precheck': 'unknown', 'usage': {}, 'completed_phases': [],
            'blocker': None, 'next_action': 'Discuss an idea, paper/blog or existing harness.',
            'note': 'Human choices and setup completion are not inferred from run records.'}


def usage(value):
    value = mapping(value)
    fields = ('budget_usd', 'normalized_usd', 'normalized_model_credits', 'model_requests')
    result = {key: number(value[key]) for key in fields
              if key in value and number(value[key]) is not None}
    state = value.get('accounting_state', value.get('model_accounting_state'))
    result['accounting_state'] = enum(state, {'settled', 'pending', 'incomplete'})
    return result


def local_status(path):
    from openrsi_space.integrations.dungeness.diagnostics import summarize
    from openrsi_space.station import name, source_hash
    path = Path(path).expanduser()
    path = path / 'run.json' if path.is_dir() else path
    run = read(path)
    result = base()
    result.update(local_run_id=name(path.parent.name),
                  harness_id=name(mapping(run.get('harness')).get('id')),
                  source_digest=source_hash(mapping(run.get('harness')).get('version')))
    result.update(source='local_record', availability='recorded',
                  execution=enum(run.get('status'), {'prepared', 'running'} | TERMINAL),
                  note='Recorded local status may be stale; it does not prove a process is still running.')
    detail = run
    record = run.get('record_path')
    if isinstance(record, str):
        record = Path(record)
        if not record.is_absolute():
            record = path.parent / record
        if record.is_file():
            detail = summarize(record)
        else:
            result['note'] = 'Runtime record unavailable; showing saved local metadata only.'
    result['usage'] = usage(detail.get('usage'))
    result['budget_cap'] = number(mapping(run.get('evaluation')).get('max_model_credits'))
    final = mapping(detail.get('final_verification'))
    result['verification'] = enum(final.get('status'), {'valid', 'invalid', 'not_retained', 'multiple_trials'})
    if result['verification'] == 'valid' and number(final.get('score')) is not None:
        result['final_score'] = number(final['score'])
    candidates = mapping(detail.get('candidate_evaluations'))
    result['candidate_evaluations'] = {key: number(candidates[key]) for key in ('evaluations', 'best_score')
                                      if number(candidates.get(key)) is not None}
    agent = mapping(detail.get('agent_execution'))
    result['agent_execution'] = {key: enum(agent.get(key), {'completed', 'failed', 'cancelled'})
                                 for key in ('last_client_status',)}
    precheck = detail.get('local_evidence_precheck_passed')
    result['evidence_precheck'] = 'passed' if precheck is True else 'failed' if precheck is False else 'unknown'
    status = result['execution']
    result['phase'] = 'prepare' if status == 'prepared' else 'local'
    result['next_action'] = 'Inspect local progress; do not start a second run.'
    if status == 'prepared':
        result['completed_phases'] = ['choose']
        result['next_action'] = 'Confirm model access and authorized budget before starting the local test.'
    elif status in TERMINAL:
        result['phase'] = 'readiness'
        result['completed_phases'] = ['choose', 'prepare', 'local']
        result['next_action'] = 'Discuss the local outcome and check matching evidence and remote authorization.'
        if result['evidence_precheck'] != 'passed':
            result['blocker'] = 'Local evidence needs inspection; do not assume eligibility or rerun automatically.'
    elif status == 'running':
        result['completed_phases'] = ['choose', 'prepare']
    elif status == 'unknown':
        result['blocker'] = 'Local execution status is missing or unsupported.'
    return result


def remote_status(state, identity):
    from openrsi_space.client import transport
    from openrsi_space.client.evaluations import RemoteClient
    from openrsi_space.contracts.results import evaluation_id
    identity = evaluation_id(identity)
    client = RemoteClient(state)
    # Do not use status(): it writes terminal results. Never publish, export a
    # receipt, retry a run or save credentials as a side effect of this command.
    session = read(client.folder(identity) / 'session.json', limit=24 * 1024 * 1024)
    if session.get('base') != client.base:
        raise OpenRSIError('Evaluator does not match saved session')
    live = json.loads(transport.solver_fetch(client.base, f'/evaluations/{identity}', client.bearer))
    bound_result(live, session['request'], identity)
    result = base()
    result.update(source='remote_api', availability='live', evaluation_id=identity,
                  execution=live['status'], phase='remote',
                  note='Authenticated status bound to the saved request; candidate scores are provisional.')
    result['completed_phases'] = ['choose', 'prepare', 'local', 'readiness']
    progress = mapping(live.get('progress'))
    result['usage'] = usage(progress.get('usage'))
    result['budget_cap'] = number(mapping(session['request'].get('evaluation')).get('max_model_credits'))
    evaluation = mapping(progress.get('evaluation'))
    result['candidate_evaluations'] = {key: number(evaluation[source])
        for key, source in (('evaluations', 'completed'), ('best_score', 'best_performance'))
        if number(evaluation.get(source)) is not None}
    result['next_action'] = f'Follow the existing run with openrsi-space remote wait {identity}.'
    if live['status'] in TERMINAL:
        result['phase'] = 'results'
        result['completed_phases'].append('remote')
        result['verification'] = ('valid' if live['status'] == 'completed' and live.get('valid') is True
                                  else 'invalid' if live.get('valid') is False else 'unknown')
        result['next_action'] = 'Discuss the verified outcome and usage; Yukon publication is optional.'
        if result['verification'] != 'valid':
            result['blocker'] = 'No confirmed valid final result; inspect owner diagnostics before another run.'
            result['next_action'] = f'Inspect openrsi-space remote diagnostics {identity}.'
    return result


def account_allowance(state):
    from openrsi_space.client.evaluations import RemoteClient
    try:
        client = RemoteClient(state)
    except (OpenRSIError, OSError, ValueError, TypeError):
        # Existing credentials are optional for a local/harness card. Never prompt.
        return {'status': 'unavailable'}
    return daily_allowance(client)


def daily_allowance(client):
    from openrsi_space.client import transport
    from openrsi_space.client.funding import amount
    try:
        value = json.loads(transport.solver_fetch(client.base, '/funding', client.bearer))
        if not isinstance(value, dict) or value.get('mode') != 'platform' or type(value.get('halted')) is not bool:
            raise ValueError('Invalid funding response')
        allowance = mapping(value.get('allowance'))
        if allowance.get('unit') != 'usd_equivalent' or allowance.get('window_seconds') != 86400:
            raise ValueError('Invalid allowance')
        limit, remaining = amount(allowance.get('limit')), amount(allowance.get('remaining'))
        if remaining > limit:
            raise ValueError('Invalid remaining allowance')
        return {'status': 'available', 'limit': float(limit), 'remaining': float(remaining),
                'halted': value['halted']}
    except (OpenRSIError, OSError, ValueError, TypeError):
        # A failed balance lookup must not hide a valid run status or echo raw responses.
        return {'status': 'unavailable'}


def status(state, *, local_run=None, evaluation=None, harness=None, station=False):
    state = Path(state)
    result = base()
    try:
        from openrsi_space.station import catalog
        if sum(value is not None for value in (local_run, evaluation, harness)) > 1:
            raise ValueError('Choose one target')
        collection = catalog(state)
        if station or harness is not None:
            result.update(availability='station', phase=None, source='workspace', **collection)
            if harness is not None:
                group = next((g for g in collection['harnesses'] if harness in (g['key'], g['harness_id'])), None)
                if group is None:
                    raise ValueError('Unknown harness')
                result.update(harness=group, harness_id=group['harness_id'],
                              next_action='Select a local run or remote evaluation to inspect its progress.')
            return present(result, state)
        if local_run is None and evaluation is None:
            locals_ = list((state / 'local').glob('*/run.json'))
            remotes = list((state / 'remote/evaluations').glob('*/session.json'))
            if len(locals_) + len(remotes) > 1:
                result.update(availability='station', phase=None, **collection,
                              next_action='Use --local-run PATH or --evaluation ID; no run was selected.',
                              local_run_count=len(locals_), remote_run_count=len(remotes))
                return present(result, state)
            elif locals_:
                local_run = locals_[0]
            elif remotes:
                evaluation = remotes[0].parent.name
        if local_run is not None:
            result = local_status(local_run)
        elif evaluation is not None:
            result = remote_status(state, evaluation)
        selected = ('remote', evaluation) if evaluation else ('local', result.get('local_run_id'))
        local_path = Path(local_run).expanduser() if local_run is not None else None
        if local_path is not None and local_path.is_dir():
            local_path = local_path / 'run.json'
        in_workspace = (local_path is not None and result.get('local_run_id') and
                        local_path.resolve() == (state / 'local' / result['local_run_id'] / 'run.json').resolve())
        group = next((g for g in collection['harnesses']
                      if (evaluation or in_workspace) and
                      any((r['kind'], r['id']) == selected for r in g['runs'])), None)
        if group:
            result.update(harness=group, harness_id=group['harness_id'])
    except (OpenRSIError, OSError, ValueError, KeyError, TypeError, AttributeError):
        # Never echo raw exceptions, logs, credentials, arbitrary status strings
        # or provider responses into the human's chat transcript.
        result.update(availability='unavailable', phase=None,
                      blocker='Could not read or validate status; no run was started or retried.',
                      next_action='Check the selected record, original --state directory, evaluator and local login.')
    return present(result, state)


def present(result, state):
    # One account-level lookup for every successful view, independent of run selection.
    if result['availability'] != 'unavailable':
        result['daily_allowance'] = account_allowance(state)
    if result['availability'] == 'station' and not result.get('harness'):
        from openrsi_space.station import overview
        result['card'] = overview(result)
    else:
        result['card'] = render(result)
    return result


def allowance_lines(allowance):
    if allowance is None:
        return []
    if allowance.get('status') != 'available':
        return ['Account allowance: unavailable']
    lines = ['Account allowance (rolling 24h):',
             f"${allowance['remaining']:.2f} available / ${allowance['limit']:g}"]
    if allowance['halted']:
        lines.append('Remote funding paused')
    return lines


def render(result):
    title = 'OPENRSI · RESEARCH STATION' if result['availability'] == 'no_records' else 'OPENRSI · HARNESS CARD'
    lines = [title, '']
    if result.get('harness'):
        from openrsi_space.station import run_lines
        group = result['harness']
        lines.extend(['Harness: ' + group['label'], ''])
        selected = ('remote', result['evaluation_id']) if result.get('evaluation_id') else ('local', result.get('local_run_id'))
        lines.extend(run_lines(group, selected, result['execution']))
        lines.append('')
    elif result.get('harness_id'):
        lines.extend(['Harness: ' + result['harness_id'], ''])
    if result.get('evaluation_id'):
        lines.extend(['Evaluation: ' + result['evaluation_id'], ''])
    elif result.get('local_run_id'):
        lines.extend(['Local run: ' + result['local_run_id'], ''])
    for key, label in PHASES if result['phase'] is not None else ():
        marker = '●' if key == result['phase'] else '✓' if key in result['completed_phases'] else '○'
        lines.append(f'{marker} {label}')
    lines.append('')
    if result['availability'] == 'no_records':
        lines.append('Now: Choose an approach together')
    elif result['availability'] != 'station':
        label = 'Last saved' if result['source'] == 'local_record' else 'Status'
        lines.append(f"{label}: {result['execution']}")
    measured = result.get('usage', {})
    amount = next((measured[key] for key in ('budget_usd', 'normalized_usd', 'normalized_model_credits')
                   if key in measured), None)
    cap = result.get('budget_cap')
    if amount is not None:
        lines.append(f'Credits used: ${amount:.2f}' + (f' / ${cap:g}' if cap is not None else ''))
    elif cap is not None:
        lines.extend([f'Budget cap: ${cap:g}', 'Credits used: unavailable'])
    lines.extend(allowance_lines(result.get('daily_allowance')))
    if result['execution'] in TERMINAL:
        outcome = {'valid': 'Valid final result', 'invalid': 'Final result invalid'}.get(
            result['verification'], 'Final result needs inspection')
        lines.append(outcome)
        if 'final_score' in result:
            lines.append(f"Score: {result['final_score']:g}")
    if result['availability'] == 'unavailable':
        next_step = 'Ask your agent to check this run.'
    elif result.get('blocker'):
        next_step = 'Review the issue with your agent.'
    else:
        next_step = {
            'choose': 'Choose an idea together.',
            'prepare': 'Confirm access and budget.',
            'local': 'Follow this run’s progress.',
            'readiness': 'Review before remote submission.',
            'remote': 'Follow this run’s progress.',
            'results': 'Explore the results together.',
        }.get(result['phase'], 'Select a run to explore.')
    lines.extend(['Next: ' + next_step, '', 'Details: Ask “Explain this run.”'])
    return box(lines)


def box(lines):
    width = 36
    wrapped = [part for line in lines for part in (textwrap.wrap(line, width=width) or [''])]
    return ('┌' + '─' * (width + 2) + '┐\n' +
            '\n'.join('│ ' + line.ljust(width) + ' │' for line in wrapped) +
            '\n└' + '─' * (width + 2) + '┘')
