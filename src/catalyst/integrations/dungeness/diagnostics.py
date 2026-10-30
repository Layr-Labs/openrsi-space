"""Bounded local diagnostics: summarize outcomes, never echo model/log bodies."""
import json
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


def summarize(record_path):
    record_path = Path(record_path)
    root = record_path.parent
    data = document(record_path).get('data', {})
    result = {'record_status': data.get('status'), 'diagnostics': []}
    usage = data.get('usage') or document(root/'usage/summary.json').get('usage', {})
    result['usage'] = usage
    result['metrics'] = data.get('metrics', {})
    paths = []
    harbor = root/'harbor'
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
        logs += sorted(harbor.glob('*/*/agent/harness-output-*.txt'))[:16]
        for path in logs:
            try:
                with path.open('rb') as stream:
                    stream.seek(max(0, path.stat().st_size - 65536))
                    text = stream.read(65536).decode('utf-8', errors='replace')
            except OSError:
                continue
            match = re.search(r'Harness exited with status (-?\d{1,5})', text)
            if match:
                result['agent_exit_code'] = int(match[1])
                result['record_status'] = 'failed'
            for marker, code, message in (
                ('Per-request output limit must be', 'output_token_limit',
                 'Request output limit exceeds the gateway cap. For Claude Code set CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000.'),
                ('Read-only file system', 'readonly_workspace',
                 'Trusted scaffold files are read-only. Do not recursively chown or modify protected paths.'),
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
                if b'gateway.model_request_rejected' not in line:
                    continue
                event = json.loads(line)
                reason = event.get('data', {}).get('code')
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
    result['local_evidence_precheck_passed'] = (result['record_status'] == 'completed'
        and usage.get('model_requests', 0) > 0 and usage.get('model_accounting_state') == 'settled')
    result['local_evidence_note'] = ('Precheck only: complete exchanges, matching source/problem/model, sufficient spending and hosted review are also required.')
    if not usage.get('model_requests', 0):
        result['diagnostics'].append({'code': 'no_accounted_model_requests',
            'message': 'No accounted model requests. This run cannot qualify as local evidence.'})
    return result
