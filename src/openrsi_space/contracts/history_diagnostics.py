"""Safe projection of a gateway history rejection, for local and owner diagnostics."""
import re

HISTORY_TYPES = frozenset("""message reasoning compaction function_call function_call_output
custom_tool_call custom_tool_call_output local_shell_call local_shell_call_output
shell_call shell_call_output apply_patch_call apply_patch_call_output tool_search_call
tool_search_output text input_text output_text thinking redacted_thinking tool_use
tool_result refusal input_image image input_audio audio document input_file file
server_tool_use web_search_call file_search_call mcp_call other""".split())
HISTORY_PATH = re.compile(
    r'(?:input|messages|system)(?:\[[0-9]{1,6}\]|\.(?:content|output|tools|tool_calls|'
    r'function|function_call|cache_control|outcome|type|role|citations|caller|allowed_callers|'
    r'reasoning_details|environment|execution|id|encrypted_content|signature|status|format|summary))*')


def history_rejection(data, request_id=None):
    if not isinstance(data, dict) or data.get('code') != 'conversation_history_rejected':
        return None
    result = {'code': 'conversation_history_rejected',
        'message': 'The gateway rejected conversation history.',
        'action': 'Keep the run records and report the request ID and structural diagnostic to the operator. '
                  'Do not remove reasoning, signatures or encrypted history to bypass validation.'}
    if type(data.get('upstream_request_sent')) is bool:
        result['upstream_request_sent'] = data['upstream_request_sent']
        result['stage'] = 'upstream' if data['upstream_request_sent'] else 'model_admission'
    for field in ('history_schema_version', 'diagnostics_version', 'item_index', 'block_index', 'field_index'):
        value = data.get(field)
        if type(value) is int and 0 <= value <= 1_000_000:
            result[field] = value
    for field, allowed in {
        'reason': {'unsupported_history_field', 'invalid_history_field', 'unsupported_history_structure'},
        'location': {'input', 'messages', 'system'},
        'field': {'id', 'encrypted_content', 'signature', 'status', 'format', 'summary', 'content'},
        'item_type': HISTORY_TYPES,
        'block_type': HISTORY_TYPES,
        'provider': {'openai', 'openai-chatgpt', 'anthropic', 'claude-subscription',
                     'openrouter', 'grok-subscription', 'minimax', 'gemini', 'other'},
        'operation': {'responses', 'responses/compact', 'chat/completions', 'messages', 'messages/count_tokens', 'other'},
        'validation_rule': {'unsupported_structure', 'unknown_field', 'expected_object', 'expected_array',
            'expected_string', 'unsupported_cache_control', 'content_depth_exceeded', 'tool_depth_exceeded',
            'unsupported_citations', 'nonlocal_tool_caller', 'unsupported_content_type', 'unsupported_role',
            'reasoning_protocol_mismatch', 'unsupported_tool_call_type', 'nonlocal_tool_discovery',
            'nonlocal_shell', 'unsupported_shell_outcome', 'unsupported_item_type', 'unsupported_tool_format',
            'unsupported_tool_type', 'unsupported_history_field', 'invalid_history_field'},
        'expected_type': {'object', 'array', 'string'},
        'actual_type': {'object', 'array', 'string', 'number', 'boolean', 'null', 'other'},
    }.items():
        value = data.get(field)
        if isinstance(value, str) and value in allowed:
            result[field] = value
    path = data.get('path')
    if isinstance(path, str) and len(path) <= 1024 and HISTORY_PATH.fullmatch(path):
        result['path'] = path
    if isinstance(request_id, str) and re.fullmatch(r'[a-f0-9-]{16,64}', request_id):
        result['request_id'] = request_id
    return result
