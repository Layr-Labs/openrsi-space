"""Shared local-evidence checks; consistency of claims, not attestation."""
import re
from catalyst.common import CatalystError, finite_number

KINDS = {'model.request', 'model.response', 'model.accounting', 'evaluation.completed'}
TERMINAL_STATUSES = ('completed', 'failed', 'cancelled')


def validate_exchanges(events, models):
    if not isinstance(events, list) or not 3 <= len(events) <= 6000:
        raise CatalystError('Provide 1–1000 complete model exchanges in a shorter local readiness run.')
    calls, successes = {}, set()
    previous_sequence = -1
    for event in events:
        if (not isinstance(event, dict) or set(event) != {'kind', 'request_id', 'sequence', 'data'}
                or event['kind'] not in KINDS or not isinstance(event['data'], dict)):
            raise CatalystError('Local evidence contains an unsupported event.')
        if type(event['sequence']) is not int or not previous_sequence < event['sequence'] <= 2**53:
            raise CatalystError('Local event sequence must be strictly increasing.')
        previous_sequence = event['sequence']
        kind, rid, data = event['kind'], event['request_id'], event['data']
        if kind == 'evaluation.completed':
            continue
        if not isinstance(rid, str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}', rid):
            raise CatalystError('A model exchange lacks a request identifier.')
        call = calls.setdefault(rid, {})
        if kind in call:
            raise CatalystError('Duplicate model event for a request identifier.')
        if kind != 'model.request' and 'model.request' not in call:
            raise CatalystError('A model response or accounting event precedes its request.')
        call[kind] = data
    if not 1 <= len(calls) <= 1000:
        raise CatalystError('Provide 1–1000 model exchanges in a shorter local readiness run.')
    for call in calls.values():
        if set(call) != {'model.request', 'model.response', 'model.accounting'}:
            raise CatalystError('Every recorded model request needs its response and accounting event.')
        accounting = call['model.accounting']
        if (accounting.get('accounting_method') != 'gateway' or accounting.get('status') != 'success'
                or type(accounting.get('total_tokens')) is not int or not 0 < accounting['total_tokens'] <= 2**53):
            raise CatalystError('Local evidence must have settled successful model accounting; retain complete exchanges from an ended run.')
        pair = (accounting.get('provider'), accounting.get('model'))
        if any((v.get('provider'), v.get('model')) != pair for v in call.values()):
            raise CatalystError('Provider or model differs within an exchange.')
        if 'request' not in call['model.request'] or 'response' not in call['model.response']:
            raise CatalystError('Include recorded model requests and responses, not accounting alone.')
        request, response = call['model.request']['request'], call['model.response']['response']
        if (not isinstance(request, dict) or not request
                or not isinstance(response, (dict, list, str)) or not response):
            raise CatalystError('Recorded model requests and responses must contain nonempty payloads.')
        successes.add(pair)
    if successes != {(m['provider'], m['name']) for m in models}:
        raise CatalystError('Every declared model needs a complete successful exchange.')
    for call in calls.values():
        usage = call['model.accounting']
        if usage.get('provider') == 'openrouter':
            if usage.get('billing_source') not in {'openrouter_usage', 'openrouter_generation'}:
                raise CatalystError('OpenRouter local evidence requires provider-reported cost for every call.')
            amount = usage.get('billed_usd')
        else:
            amount = usage.get('normalized_usd')
        try:
            finite_number(amount, nonnegative=True)
        except CatalystError:
            raise CatalystError('Every model accounting event needs finite settled spending; unknown usage is not zero.') from None
    return calls
