"""Export a private readiness transcript, separate from public harness source.

This is a solver-authored claim. It is not an attestation or a replay proof.
"""
from openrsi_space.compatibility import EVIDENCE_PROTOCOL
import json
import sys
import uuid
from pathlib import Path
from openrsi_space.common import OpenRSIError, canonical
from openrsi_space.contracts.results import digest
from .local_check import validate_record, _record

MAX_BYTES = 192 * 1024 * 1024
KINDS = {'model.request','model.response','model.accounting','evaluation.completed'}


def bundle(path, body):
    check = validate_record(Path(path), body)
    record_path, record = _record(Path(check['record_path']))
    events = []
    size = 0
    with (record_path.parent / 'usage/events.jsonl').open() as stream:
        for line in stream:
            if len(line.encode()) > MAX_BYTES:
                raise OpenRSIError('A local event exceeds 192 MiB. Use a shorter readiness test.')
            event = json.loads(line)
            if event.get('run_id') != check['run_id'] or event.get('kind') not in KINDS:
                continue
            # Only known runtime event payloads, never environment, headers, local
            # login files, arbitrary paths, generated circuits or a whole archive.
            data = event.get('data', {})
            keys = {'model.request': {'model','provider','operation','request'},
                    'model.response': {'model','provider','operation','status','content_type','response'},
                    'model.accounting': {'model','provider','status','accounting_method','total_tokens',
                                         'input_tokens','output_tokens','normalized_usd','billed_usd','billing_source',
                                         'upstream_request_id'},
                    'evaluation.completed': {'status','score','metrics'}}[event['kind']]
            item = {'kind':event['kind'], 'request_id':event.get('request_id'), 'sequence':event.get('sequence'),
                    'data':{k:v for k,v in data.items() if k in keys}}
            size += len(canonical(item))
            if size > MAX_BYTES or len(events) >= 6000:
                raise OpenRSIError('Private local evidence exceeds the upload limit. Run a shorter local readiness test; logs are not silently truncated.')
            events.append(item)
    document = {'protocol':EVIDENCE_PROTOCOL, 'source_digest':body['source']['digest'],
                'problem_digest':digest(body['problem_set']), 'models':check['models'],
                'run_id':check['run_id'], 'runtime_revision':record['data']['configuration']['repository'].get('commit') or 'unknown',
                'status':check['local_run_status'], 'events':events, 'local_budget_cap_usd':check['local_budget_cap_usd']}
    from openrsi_space.contracts.local_evidence import validate_exchanges
    validate_exchanges(events, check['models'])
    if len(canonical(document)) > MAX_BYTES:
        raise OpenRSIError('Private local evidence exceeds 192 MiB. Use a shorter local readiness run.')
    return document


def attach(client, body, local_check):
    if not local_check:
        raise OpenRSIError('Platform funding requires a local readiness record. Use --local-run PATH; no remote run was submitted.')
    if local_check.get('local_evidence'):
        # Resume the same operation with the same immutable uploaded evidence.
        body['local_evidence'] = local_check['local_evidence']
        return
    if not local_check.get('record_path'):
        raise OpenRSIError('The saved request has no local evidence. Supply --local-run PATH; no new run was submitted.')
    from . import transport
    print('Preparing local-run evidence; no remote inference has started.',file=sys.stderr,flush=True)
    document = bundle(local_check.get('local_run_path') or local_check['record_path'], body)
    print(f'Uploading local-run evidence ({len(canonical(document))/1048576:.1f} MiB)...',
          file=sys.stderr,flush=True)
    try:
        reply = json.loads(transport.solver_fetch(client.base, '/local-evidence', client.bearer, document=document))
    except transport.HTTPFailure as error:
        from .state import private_json
        from openrsi_space.common import now
        error.before_evaluation = True
        diagnostic = client.state / 'remote/diagnostics' / ('upload-' + str(uuid.uuid4()) + '.json')
        try:
            private_json(diagnostic, {'schema_version':1, 'at':now(), 'operation':'local_evidence_upload',
                'request_id':None, 'http_status':error.status, 'details':error.details})
            error.diagnostic_path = diagnostic
        except OSError:
            error.diagnostic_write_failed = True
        raise
    expected = digest(document)
    if reply != {'protocol':EVIDENCE_PROTOCOL,'digest':expected,'private':True}:
        raise OpenRSIError('Local evidence upload returned an invalid binding.')
    body['local_evidence'] = expected
    print('Local-run evidence uploaded; submission screening has not started yet.',file=sys.stderr,flush=True)
