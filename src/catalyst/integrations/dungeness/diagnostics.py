"""Bounded local diagnostics: summarize outcomes, never echo model/log bodies."""
import json
import math
from pathlib import Path
import re


def document(path):
    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            return {}
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def candidate_summary(data, usage_summary):
    """Report evaluator observations, not scores printed by an agent."""
    evaluation = data.get('evaluation') or usage_summary.get('evaluation', {})
    if not isinstance(evaluation, dict):
        evaluation = {}
    count = evaluation.get('submissions_used')
    score = evaluation.get('best_score')
    valid_score = type(score) in (int, float) and math.isfinite(score) and score >= 0
    result = {'status': 'valid_observed' if valid_score else 'unknown',
              'scope': 'best local evaluator observation; not final-candidate verification'}
    if type(count) is int and count >= 0:
        result['evaluations'] = count
        if not valid_score:
            result['status'] = 'no_valid_observed' if count else 'not_evaluated'
    if valid_score:
        result['best_score'] = score
    return result


def reported_agent_outcome(text):
    """Recognize bounded structured terminal events, without exposing log text.

    Nested client failures do not override the harness exit code: a harness can
    recover, or stop normally after saving a candidate. Keep that distinction.
    """
    result = {}
    reasons = {'api_error', 'success', 'completed', 'budget_exhausted',
               'max_turns', 'max_tokens', 'timeout', 'cancelled',
               'sessions made no metered progress'}
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get('type') in ('turn.failed', 'turn.completed'):
            result.update(last_client_status='failed' if event['type'] == 'turn.failed' else 'completed',
                          last_client_stop_reason='api_error' if event['type'] == 'turn.failed' else 'completed')
            result.pop('last_client_http_status', None)
            result.pop('last_client_exit_code', None)
        if event.get('event') == 'codex_finished' and type(event.get('exit_code')) is int:
            code = event['exit_code']
            result.update(last_client_status='failed' if code else 'completed',
                          last_client_exit_code=code,
                          last_client_stop_reason='nonzero_exit' if code else 'completed')
        if event.get('type') == 'result' and type(event.get('is_error')) is bool:
            result['last_client_status'] = 'failed' if event['is_error'] else 'completed'
            reason = event.get('terminal_reason')
            result['last_client_stop_reason'] = reason if isinstance(reason, str) and reason in reasons else 'unspecified'
            result.pop('last_client_http_status', None)
            status = event.get('api_error_status')
            if type(status) is int and 100 <= status <= 599:
                result['last_client_http_status'] = status
        if event.get('event') == 'stop':
            reason = event.get('reason')
            result['harness_stop_reason'] = reason if isinstance(reason, str) and reason in reasons else 'unspecified'
    return result


def final_verification(harbor):
    """Read trusted verifier outputs, never infer validity from reward sentinels."""
    trials = []
    for path in sorted(harbor.glob('*/*/verifier/score.json'))[:32]:
        data = document(path)
        score = data.get('score')
        status = data.get('status')
        valid = status == 'ok' and type(score) in (int, float) and math.isfinite(score) and score >= 0
        item = {'status': 'valid' if valid else 'invalid' if status == 'invalid' else 'unknown',
                'path': str(path)}
        if valid:
            item['score'] = score
            for key in ('avg_toffoli', 'peak_qubits'):
                value = data.get(key)
                if type(value) in (int, float) and math.isfinite(value) and value >= 0:
                    item[key] = value
        trials.append(item)
    return ({**trials[0], 'trials': trials} if len(trials) == 1 else
            {'status': 'multiple_trials' if trials else 'not_retained', 'trials': trials})


def summarize(record_path):
    record_path = Path(record_path)
    root = record_path.parent
    data = document(record_path).get('data', {})
    result = {'record_status': data.get('status'), 'runtime_record_status': data.get('status'), 'diagnostics': []}
    usage_summary = document(root/'usage/summary.json')
    usage = data.get('usage') or usage_summary.get('usage', {})
    result['usage'] = usage
    result['metrics'] = dict(data.get('metrics') or {})
    result['candidate_evaluations'] = candidate_summary(data, usage_summary)
    metric = data.get('metric', {}).get('name')
    if isinstance(metric, str) and 'best_score' in result['candidate_evaluations']:
        result['metrics'].setdefault(metric, result['candidate_evaluations']['best_score'])
    paths = []
    harbor = root/'harbor'
    result['final_verification'] = final_verification(harbor)
    if isinstance(metric, str) and result['final_verification']['status'] == 'valid':
        result['metrics'].setdefault(metric, result['final_verification']['score'])
    if harbor.is_dir():
        paths = sorted(harbor.glob('*/*/agent/harness-outcome.json'))[:32]
        for path in paths:
            outcome = document(path)
            code = outcome.get('exit_code')
            if type(code) is int:
                result['agent_exit_code'] = code
                if code != 0:
                    result['record_status'] = 'failed'
                    result['diagnostics'].append({'code': 'harness_exit', 'exit_code': code,
                        'message': f'Harness exited with status {code}.', 'path': str(path)})
        # Older runtimes lack structured outcomes. Inspect only bounded tails,
        # returning fixed messages and paths, never arbitrary submitted text.
        logs = sorted(harbor.glob('*/*/exception.txt'))[:16]
        logs += sorted(harbor.glob('*/*/agent/harness-output-*.txt'),
                       key=lambda p: (str(p.parent), int(p.stem.rsplit('-', 1)[-1])
                                      if p.stem.rsplit('-', 1)[-1].isdigit() else -1))[-16:]
        for path in logs:
            try:
                with path.open('rb') as stream:
                    stream.seek(max(0, path.stat().st_size - 65536))
                    text = stream.read(65536).decode('utf-8', errors='replace')
            except OSError:
                continue
            if path.name.startswith('harness-output-'):
                reported = reported_agent_outcome(text)
                if reported:
                    result['agent_reported_outcome'] = {**reported, 'path': str(path)}
            match = re.search(r'Harness exited with status (-?\d{1,5})', text)
            if match:
                result['agent_exit_code'] = int(match[1])
                result['record_status'] = 'failed'
            for marker, code, message in (
                ('Per-request output limit must be', 'output_token_limit',
                 'Request output limit exceeds the gateway cap. For Claude Code set CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000.'),
                ('Read-only file system', 'readonly_workspace',
                 'Trusted scaffold files are read-only. Do not recursively chown or modify protected paths.'),
                ('Invalid cross-device link', 'workspace_cross_device_operation',
                 'A filesystem operation crossed a mount boundary or tried to replace a mount root. '
                 'Inspect the failed operation in the retained log. For candidate restore, copy contents '
                 'into the existing directory, or write through a mounted file; do not rename the mount root. '
                 'Snapshot-and-restore harnesses are supported. See docs/executable-harness.md#workspace-filesystem-contract.'),
                ('Permission denied', 'workspace_permissions',
                 'Check writable workspace ownership for the harness user; trusted scaffold files remain read-only.'),
            ):
                if marker.lower() in text.lower():
                    result['diagnostics'].append({'code': code, 'message': message, 'path': str(path)})
        if logs and any(p.name == 'exception.txt' for p in logs):
            result['record_status'] = 'failed'
            result['diagnostics'].append({'code': 'harbor_trial_failed',
                'message': 'A Harbor trial failed. Inspect the local exception file.',
                'path': str(next(p for p in logs if p.name == 'exception.txt'))})
    event_path = root/'usage/events.jsonl'
    try:
        # Early admission failures precede any model calls; retain the first one.
        with event_path.open('rb') as stream:
            for _ in range(10000):
                line = stream.readline(65537)
                if not line:
                    break
                if len(line) > 65536:
                    while line and not line.endswith(b'\n'):
                        line = stream.readline(65537)
                    continue
                if b'gateway.model_request_rejected' not in line and b'gateway.budget_rejected' not in line:
                    continue
                event = json.loads(line)
                details = event.get('data', {})
                reason = details.get('code')
                if (event.get('kind') == 'gateway.budget_rejected'
                        and reason == 'model_reservation_exceeds_remaining_budget'
                        and details.get('upstream_request_sent') is False):
                    transient = details.get('retryable') is True
                    finding = {'code': reason, 'upstream_request_sent': False,
                        'retryable': transient, 'path': str(event_path),
                        'message': ('Request was not sent to the provider. Wait for active calls to settle before retrying.'
                            if transient else 'Request was not sent to the provider. Reduce input or the per-request output limit, or choose a sufficient run budget.')}
                    for field in ('available_usd', 'required_reservation_usd'):
                        value = details.get(field)
                        if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1e9:
                            finding[field] = value
                    result['diagnostics'].append(finding)
                    break
                if reason in {'output_token_limit', 'request_policy_rejected'}:
                    maximum = event.get('data', {}).get('maximum', 65536)
                    maximum = maximum if type(maximum) is int and 1 <= maximum <= 1048576 else 65536
                    result['diagnostics'].append({'code': reason,
                        'message': (f'Per-request output tokens must be 1..{maximum}; set a compatible client limit.'
                                    if reason == 'output_token_limit' else 'Gateway rejected the request before inference; check the request policy.'),
                        'path': str(event_path)})
                    break
    except (OSError, ValueError):
        pass
    if result['record_status'] in {'failed', 'cancelled'} and not result['diagnostics']:
        result['diagnostics'].append({'code': 'runtime_trial_failed',
            'message': 'Dungeness recorded an unsuccessful trial. Inspect the retained run record and Harbor logs.',
            'path': str(record_path)})
    # A failed final save does not erase complete local model exchanges. Keep
    # the failed execution status, and report evidence readiness separately.
    from catalyst.client.local_check import check_recorded_calls, record_models
    from catalyst.contracts.local_evidence import TERMINAL_STATUSES
    result['local_evidence_precheck_passed'] = False
    result['local_evidence_precheck'] = {'status': 'not_ready', 'reason': 'run_not_ended'}
    if data.get('status') in TERMINAL_STATUSES:
        result['local_evidence_precheck']['reason'] = 'missing_or_incomplete_model_exchanges'
        try:
            agent = data['configuration']['sources']['agent']['document']
            models = agent.get('model_access', {}).get('models') or [data['model']]
            check_recorded_calls(record_path, data, record_models(models))
            result['local_evidence_precheck_passed'] = True
            result['local_evidence_precheck'] = {'status': 'passed', 'reason': 'complete_settled_model_exchanges'}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
    if result['local_evidence_precheck_passed'] and result['record_status'] != 'completed':
        result['diagnostics'].append({'code': 'failed_run_evidence_available',
            'message': 'The run failed, but retained model exchanges are complete and accounting is settled. '
                       'The original unchanged harness may still qualify for submission; source, problem, '
                       'model, budget-cap matching and hosted review remain required.'})
    result['local_evidence_note'] = ('Precheck only: complete exchanges, matching source/problem/model/reasoning, '
        'a recorded local budget cap covering the remote request, and hosted review are also required. '
        'Actual local spending may be lower. Agent-reported outcomes are diagnostic, not independent verification.')
    if result.get('agent_reported_outcome', {}).get('last_client_status') == 'failed':
        result['diagnostics'].append({'code': 'nested_agent_failure',
            'message': 'The last reported model-client session failed. Check its stop reason and gateway diagnostics; '
                       'the harness exit code, retained candidate and evidence precheck are reported separately.',
            'path': result['agent_reported_outcome']['path']})
    if usage.get('model_requests', 0) and usage.get('model_accounting_state') != 'settled':
        result['diagnostics'].append({'code': 'model_accounting_unsettled',
            'message': 'Model accounting is incomplete, often after an interrupted call. Unknown usage is not zero. This run cannot qualify as local evidence; retain its logs for diagnosis.',
            'path': str(event_path)})
    if not usage.get('model_requests', 0):
        result['diagnostics'].append({'code': 'no_accounted_model_requests',
            'message': 'No accounted model requests. This run cannot qualify as local evidence.'})
    result['agent_execution'] = {
        'wrapper_status': result['record_status'],
        'wrapper_exit_code': result.get('agent_exit_code'),
        'last_client_status': result.get('agent_reported_outcome', {}).get('last_client_status', 'unknown'),
    }
    return result
