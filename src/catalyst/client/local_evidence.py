"""Export a private readiness transcript, separate from public harness source.

This is a solver-authored claim. It is not an attestation or a replay proof.
"""
import json
from pathlib import Path
from catalyst.common import CatalystError, canonical
from catalyst.contracts.results import digest
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
                raise CatalystError('A local event exceeds 192 MiB. Use a shorter readiness test.')
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
                raise CatalystError('Private local evidence exceeds the upload limit. Run a shorter local readiness test; logs are not silently truncated.')
            events.append(item)
    document = {'protocol':'catalyst-local-evidence-v1', 'source_digest':body['source']['digest'],
                'problem_digest':digest(body['problem_set']), 'models':check['models'],
                'run_id':check['run_id'], 'runtime_revision':record['data']['configuration']['repository'].get('commit') or 'unknown',
                'status':'completed', 'events':events}
    from decimal import Decimal, InvalidOperation
    try:
        amounts = []
        for event in events:
            if event['kind'] != 'model.accounting':
                continue
            data = event['data']
            if data.get('provider') == 'openrouter':
                if data.get('billing_source') not in {'openrouter_usage', 'openrouter_generation'}:
                    raise CatalystError('OpenRouter local evidence requires provider-reported cost. Update Dungeness and use a run with complete provider accounting.')
                amounts.append(data.get('billed_usd'))
            else:
                amounts.append(data.get('normalized_usd'))
        if not amounts or any(isinstance(n,bool) or not isinstance(n,(int,float)) for n in amounts):
            raise ValueError
        spent = sum((Decimal(str(n)) for n in amounts), Decimal(0))
        minimum = Decimal(str(body['evaluation']['max_model_credits']))
        if any(not Decimal(str(n)).is_finite() or n<0 for n in amounts):
            raise ValueError
        if spent < minimum:
            raise CatalystError(f'Recorded local spending is {spent} credits; at least {minimum} is required '
                                'for this remote budget. Provide a larger matching local run or lower --budget.')
    except CatalystError:
        raise
    except (ValueError, InvalidOperation):
        raise CatalystError('Local evidence needs settled spending for every model request (provider-reported cost for OpenRouter).') from None
    if len(canonical(document)) > MAX_BYTES:
        raise CatalystError('Private local evidence exceeds 192 MiB. Use a shorter local readiness run.')
    return document


def attach(client, body, local_check):
    if not local_check:
        raise CatalystError('Platform funding requires a local readiness record. Use --local-run PATH; no remote run was submitted.')
    if local_check.get('local_evidence'):
        # Resume the same operation with the same immutable uploaded evidence.
        body['local_evidence'] = local_check['local_evidence']
        return
    if not local_check.get('record_path'):
        raise CatalystError('The saved request has no local evidence. Supply --local-run PATH; no new run was submitted.')
    from . import transport
    document = bundle(local_check['record_path'], body)
    reply = json.loads(transport.solver_fetch(client.base, '/local-evidence', client.bearer, document=document))
    expected = digest(document)
    if reply != {'protocol':'catalyst-local-evidence-v1','digest':expected,'private':True}:
        raise CatalystError('Local evidence upload returned an invalid binding.')
    body['local_evidence'] = expected
