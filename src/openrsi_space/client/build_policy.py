"""Anonymous discovery of the hosted builder's effective dependency policy."""
from openrsi_space.compatibility import BUILD_POLICY_PROTOCOL
import json
import re
from openrsi_space.common import OpenRSIError
from . import transport

PROTOCOL = BUILD_POLICY_PROTOCOL


def validate(value):
    def label(text):
        return isinstance(text, str) and bool(re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,252}', text))
    if (not isinstance(value, dict) or value.get('protocol') != PROTOCOL
            or not label(value.get('version'))
            or not isinstance(value.get('digest'), str)
            or not re.fullmatch(r'[a-f0-9]{64}', value['digest'])
            or type(value.get('operator_override')) is not bool
            or not isinstance(value.get('enabled_profiles'), list)
            or len(value['enabled_profiles']) > 16
            or not all(label(x) for x in value['enabled_profiles'])
            or not isinstance(value.get('rules'), list) or not 1 <= len(value['rules']) <= 128):
        raise OpenRSIError('Evaluator returned an invalid build dependency policy.')
    rules = []
    for rule in value['rules']:
        if (not isinstance(rule, dict) or not label(rule.get('host'))
                or type(rule.get('include_subdomains')) is not bool):
            raise OpenRSIError('Evaluator returned an invalid dependency host rule.')
        rules.append({'host': rule['host'], 'include_subdomains': rule['include_subdomains']})
    return {key: value[key] for key in ('protocol', 'version', 'digest', 'operator_override', 'enabled_profiles')} | {'rules': rules}


def policy(base=None):
    raw = transport.fetch((base or transport.endpoint()) + '/public/build-policy', None, limit=65536)
    return validate(json.loads(raw))
