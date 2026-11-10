"""Workspace-local harness cards assembled from existing run records, offline."""
from datetime import datetime
from itertools import islice
import re

from openrsi_space.contracts.results import bound_result
from openrsi_space.client.transport import safe_uuid
from openrsi_space.common import OpenRSIError
from openrsi_space.journey import read, mapping, enum, box


def name(value):
    return value if isinstance(value, str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', value) else None


def source_hash(value):
    return value if isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) else None


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() if isinstance(value, str) else 0
    except (ValueError, OverflowError, OSError):
        return 0


def catalog(state):
    """Never contact every run's evaluator merely to display a collection."""
    runs, remotes, omitted = [], [], 0
    paths = list(islice((state / 'local').glob('*/run.json'), 201))
    paths += list(islice((state / 'remote/evaluations').glob('*/session.json'), 201))
    truncated = len(paths) > 200
    for path in sorted(paths, key=str)[:200]:
        kind = 'local' if path.name == 'run.json' else 'remote'
        identity = name(path.parent.name) if kind == 'local' else safe_uuid(path.parent.name)
        if not identity:
            omitted += 1
            continue
        try:
            data = read(path, limit=24 * 1024 * 1024 if kind == 'remote' else 2 * 1024 * 1024)
            run = {'id': identity, 'kind': kind, 'execution': 'unknown',
                   'source_digest': None, 'linked_local_run': None,
                   'created_at_order': timestamp(data.get('created_at'))}
            if kind == 'local':
                harness = mapping(data.get('harness'))
                run.update(harness_id=name(harness.get('id')),
                           source_digest=source_hash(harness.get('version')),
                           execution=enum(data.get('status'), {'prepared', 'running', 'completed', 'failed', 'cancelled'}))
                runs.append(run)
            else:
                request = mapping(data.get('request'))
                run['source_digest'] = source_hash(mapping(request.get('source')).get('digest'))
                result_path = path.parent / 'result.json'
                if result_path.is_file():
                    try:
                        result = read(result_path)
                        bound_result(result, request, identity)
                        run['execution'] = result['status']
                    except (OSError, ValueError, KeyError, TypeError, OpenRSIError):
                        pass
                remotes.append((run, mapping(data.get('local_check'))))
        except (OSError, ValueError, TypeError):
            omitted += 1
    for run, check in remotes:
        matches = [local for local in runs if local['kind'] == 'local'
                   and run['source_digest'] and local['source_digest'] == run['source_digest']]
        linked = next((local for local in matches if local['id'] == check.get('run_id')), None)
        ids = {local['harness_id'] for local in matches if local.get('harness_id')}
        run['harness_id'] = linked.get('harness_id') if linked else next(iter(ids)) if len(ids) == 1 else None
        if linked:
            run['linked_local_run'] = linked['id']
        runs.append(run)
    groups = {}
    for run in runs:
        identity = run.get('harness_id')
        key = ('harness:' + identity if identity else 'source:' + run['source_digest']
               if run['source_digest'] else 'run:' + run['kind'] + ':' + run['id'])
        group = groups.setdefault(key, {'key': key, 'harness_id': identity,
            'label': identity or ('Source ' + run['source_digest'][:12] if run['source_digest'] else 'Unidentified harness'),
            'runs': []})
        group['runs'].append(run)
    for group in groups.values():
        group['runs'].sort(key=lambda r: (r['created_at_order'], r['id']), reverse=True)
        for run in group['runs']:
            run.pop('created_at_order')
    return {'harnesses': sorted(groups.values(), key=lambda g: g['key']),
            'omitted_records': omitted, 'truncated': truncated}


def run_lines(group, selected=None, current=None):
    chosen = next((r for r in group['runs'] if (r['kind'], r['id']) == selected), None)
    visible = group['runs'][:5]
    if chosen and chosen not in visible:
        visible = visible[:4] + [chosen]
    lines = ['Runs (saved status)']
    for run in visible:
        marker = '▶' if (run['kind'], run['id']) == selected else ' '
        identity = run['id'][:8] + '…' if run['kind'] == 'remote' else run['id']
        lines.append(f"{marker} {run['kind'].title()} {identity}")
        value = current if (run['kind'], run['id']) == selected and current != 'unknown' and current else run['execution']
        lines.append('  ' + value)
    if len(group['runs']) > len(visible):
        lines.append(f"+ {len(group['runs']) - len(visible)} other runs (full list in JSON)")
    return lines


def overview(data):
    lines = ['MY RESEARCH STATION', '', 'Harness cards · this workspace', 'Saved status; no remote refresh', '']
    for index, group in enumerate(data['harnesses'], 1):
        local = sum(r['kind'] == 'local' for r in group['runs'])
        lines.extend([f"[{index}] {group['label']}", f"    {local} local · {len(group['runs']) - local} remote"])
    if not data['harnesses']:
        lines.append('No run records yet.')
    if data['omitted_records']:
        lines.append(f"{data['omitted_records']} unreadable records omitted.")
    if data['truncated']:
        lines.append('Collection limited to 200 records.')
    lines.extend(['', 'Open: journey status --harness ID', 'Or select --local-run / --evaluation', 'Numbers apply only to this view.'])
    return box(lines)
