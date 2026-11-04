"""Shared local-evidence checks; consistency of claims, not attestation."""
import re
from openrsi_space.common import OpenRSIError, finite_number

KINDS = {'model.request', 'model.response', 'model.accounting', 'evaluation.completed'}
TERMINAL_STATUSES = ('completed', 'failed', 'cancelled')


def validate_exchanges(events, models):
    if not isinstance(events, list) or not 3 <= len(events) <= 6000:
        raise OpenRSIError('Provide 1–1000 complete model exchanges in a shorter local readiness run.')
    calls, successes = {}, set()
    previous_sequence = -1
    for event in events:
        if (not isinstance(event, dict) or set(event) != {'kind', 'request_id', 'sequence', 'data'}
                or event['kind'] not in KINDS or not isinstance(event['data'], dict)):
            raise OpenRSIError('Local evidence contains an unsupported event.')
        if type(event['sequence']) is not int or not previous_sequence < event['sequence'] <= 2**53:
            raise OpenRSIError('Local event sequence must be strictly increasing.')
        previous_sequence = event['sequence']
        kind, rid, data = event['kind'], event['request_id'], event['data']
        if kind == 'evaluation.completed':
            continue
        if not isinstance(rid, str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}', rid):
            raise OpenRSIError('A model exchange lacks a request identifier.')
        call = calls.setdefault(rid, {})
        if kind in call:
            raise OpenRSIError('Duplicate model event for a request identifier.')
        if kind != 'model.request' and 'model.request' not in call:
            raise OpenRSIError('A model response or accounting event precedes its request.')
        call[kind] = data
    if not 1 <= len(calls) <= 1000:
        raise OpenRSIError('Provide 1–1000 model exchanges in a shorter local readiness run.')
    for call in calls.values():
        if set(call) != {'model.request', 'model.response', 'model.accounting'}:
            raise OpenRSIError('Every recorded model request needs its response and accounting event.')
        accounting = call['model.accounting']
        if (accounting.get('accounting_method') != 'gateway' or accounting.get('status') != 'success'
                or type(accounting.get('total_tokens')) is not int or not 0 < accounting['total_tokens'] <= 2**53):
            raise OpenRSIError('Local evidence must have settled successful model accounting; retain complete exchanges from an ended run.')
        pair = (accounting.get('provider'), accounting.get('model'))
        if any((v.get('provider'), v.get('model')) != pair for v in call.values()):
            raise OpenRSIError('Provider or model differs within an exchange.')
        if 'request' not in call['model.request'] or 'response' not in call['model.response']:
            raise OpenRSIError('Include recorded model requests and responses, not accounting alone.')
        request, response = call['model.request']['request'], call['model.response']['response']
        if (not isinstance(request, dict) or not request
                or not isinstance(response, (dict, list, str)) or not response):
            raise OpenRSIError('Recorded model requests and responses must contain nonempty payloads.')
        successes.add(pair)
    if successes != {(m['provider'], m['name']) for m in models}:
        raise OpenRSIError('Every declared model needs a complete successful exchange.')
    for call in calls.values():
        usage = call['model.accounting']
        if usage.get('provider') == 'openrouter':
            if usage.get('billing_source') not in {'openrouter_usage', 'openrouter_generation'}:
                raise OpenRSIError('OpenRouter local evidence requires provider-reported cost for every call.')
            amount = usage.get('billed_usd')
        else:
            amount = usage.get('normalized_usd')
        try:
            finite_number(amount, nonnegative=True)
        except OpenRSIError:
            raise OpenRSIError('Every model accounting event needs finite settled spending; unknown usage is not zero.') from None
    return calls
