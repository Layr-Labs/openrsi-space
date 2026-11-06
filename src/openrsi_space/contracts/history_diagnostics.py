"""Safe projection of a gateway history rejection, for local and owner diagnostics."""
import re


def history_rejection(data, request_id=None):
    if not isinstance(data, dict) or data.get('code') != 'conversation_history_rejected':
        return None
    result = {'code': 'conversation_history_rejected',
        'message': 'The gateway rejected conversation history.',
        'action': 'Update to the supported runtime or contact the operator with the request ID. '
                  'Do not remove reasoning, signatures or encrypted history to bypass validation.'}
    if type(data.get('upstream_request_sent')) is bool:
        result['upstream_request_sent'] = data['upstream_request_sent']
        result['stage'] = 'upstream' if data['upstream_request_sent'] else 'model_admission'
    for field in ('history_schema_version', 'item_index', 'field_index'):
        value = data.get(field)
        if type(value) is int and 0 <= value <= 1_000_000:
            result[field] = value
    for field, allowed in {
        'reason': {'unsupported_history_field', 'invalid_history_field', 'unsupported_history_structure'},
        'location': {'input', 'messages', 'system'},
        'field': {'id', 'encrypted_content', 'signature', 'status', 'format', 'summary', 'content'},
        'item_type': {'reasoning'},
    }.items():
        value = data.get(field)
        if isinstance(value, str) and value in allowed:
            result[field] = value
    if isinstance(request_id, str) and re.fullmatch(r'[a-f0-9-]{16,64}', request_id):
        result['request_id'] = request_id
    return result
