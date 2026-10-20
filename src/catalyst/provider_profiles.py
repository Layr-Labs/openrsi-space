"""Trusted profiles for providers using the existing OpenAI wire protocol.

This module and providers.json also ship in Dungeness's gateway build context.
Profiles are operator configuration, never accepted from a harness/run request.
"""
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

BUILTINS = frozenset({'openai', 'openai-chatgpt', 'anthropic', 'openrouter', 'moonshot', 'kimi-code'})
PROFILE_PATH = Path(__file__).with_name('providers.json')


def load_profiles(path=PROFILE_PATH):
    document = json.loads(Path(path).read_text())
    if (not isinstance(document, dict) or set(document) != {'schema_version', 'providers'}
            or type(document['schema_version']) is not int or document['schema_version'] != 1):
        raise ValueError('Invalid trusted provider registry.')
    profiles = document['providers']
    if not isinstance(profiles, dict):
        raise ValueError('Provider registry must contain a mapping.')
    keys = {'protocol', 'base_url', 'credential_env', 'credential_kind', 'billed',
            'routes', 'headers', 'model_header', 'models', 'catalog_author'}
    optional = {'credential_header', 'credential_prefix', 'credential_headers'}
    for name, item in profiles.items():
        if name in BUILTINS or not re.fullmatch(r'[a-z][a-z0-9-]{0,47}', name):
            raise ValueError('Provider registry name conflicts with a builtin or is invalid.')
        if (not isinstance(item, dict) or not keys <= set(item)
                or set(item) - keys - optional or item['protocol'] != 'openai'):
            raise ValueError('Unsupported provider profile fields or wire protocol.')
        if not isinstance(item['base_url'], str) or any(ord(c) < 33 or ord(c) > 126 for c in item['base_url']):
            raise ValueError('Invalid fixed provider URL.')
        url = urlsplit(item['base_url'])
        if (url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment
                or not url.path.startswith('/')):
            raise ValueError('Provider upstream must be a fixed HTTPS URL.')
        if (not isinstance(item['credential_env'], str)
                or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', item['credential_env'])
                or item['credential_kind'] not in {'api-key', 'session-token'} or type(item['billed']) is not bool):
            raise ValueError('Invalid provider credential configuration.')
        if not isinstance(item['routes'], list) or not item['routes'] or not set(item['routes']) <= {'responses', 'chat/completions'}:
            raise ValueError('Configured providers support only metered text inference routes.')
        if item['credential_env'] in {'OPENAI_API_KEY', 'OPENROUTER_API_KEY', 'ANTHROPIC_API_KEY', 'MOONSHOT_API_KEY', 'KIMI_CODE_API_KEY', 'PATH', 'HOME'} or item['credential_env'].endswith('_EXPIRES_AT'):
            raise ValueError('Provider credential environment collides with a reserved name.')
        if not isinstance(item['headers'], dict):
            raise ValueError('Provider headers must be a mapping.')
        credential_header = item.get('credential_header', 'authorization')
        prefix = item.get('credential_prefix', 'Bearer ')
        extra = item.get('credential_headers', {})
        forbidden = {'host', 'content-type', 'content-length', 'transfer-encoding',
                     'connection', 'accept', 'accept-encoding', 'user-agent', 'cookie',
                     'proxy-authorization'}
        if (not isinstance(credential_header, str)
                or not re.fullmatch(r'[a-z][a-z0-9-]*', credential_header)
                or credential_header in forbidden or not isinstance(prefix, str)
                or any(ord(c) < 32 or ord(c) > 126 for c in prefix)
                or not isinstance(extra, dict)):
            raise ValueError('Invalid configured authentication headers.')
        for header, env in extra.items():
            if (not isinstance(header, str) or not re.fullmatch(r'[a-z][a-z0-9-]*', header)
                    or header in forbidden | {'authorization', 'x-api-key', credential_header}
                    or not isinstance(env, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}', env)
                    or not env.startswith(item['credential_env'] + '_') or env.endswith('_EXPIRES_AT')):
                raise ValueError('Invalid additional credential header.')
        auth_names = {credential_header, *extra}
        if auth_names & set(item['headers']) or item['model_header'] in auth_names:
            raise ValueError('Authentication headers must not overlap fixed or model headers.')
        if item['model_header'] in item['headers']:
            raise ValueError('Model routing header must not also be a fixed header.')
        names = list(item['headers']) + ([item['model_header']] if item['model_header'] else [])
        for header in names:
            if not isinstance(header, str) or not re.fullmatch(r'x-[a-z0-9-]+', header):
                raise ValueError('Only fixed x-* provider headers can be configured.')
        for value in item['headers'].values():
            if not isinstance(value, str) or not value or any(ord(c) < 32 or ord(c) > 126 for c in value):
                raise ValueError('Invalid provider header value.')
        if not isinstance(item['catalog_author'], str) or not re.fullmatch(r'[a-z0-9-]+', item['catalog_author']):
            raise ValueError('Invalid reference catalog author.')
        if not isinstance(item['models'], dict):
            raise ValueError('Provider model mappings must be a mapping.')
        for model, mapping in item['models'].items():
            if (not re.fullmatch(r'[A-Za-z0-9._:-]{1,120}', model)
                    or not isinstance(mapping, dict) or set(mapping) != {'upstream', 'catalog'}
                    or not isinstance(mapping['upstream'], str)
                    or not re.fullmatch(r'[A-Za-z0-9._:-]{1,120}', mapping['upstream'])
                    or not isinstance(mapping['catalog'], str)
                    or not re.fullmatch(re.escape(item['catalog_author']) + r'/[A-Za-z0-9._:-]{1,120}', mapping['catalog'])):
                raise ValueError('Invalid fixed model mapping.')
        if item['credential_kind'] == 'session-token' and not item['models']:
            raise ValueError('Subscription profiles require explicit model/pricing mappings.')
    environments = [env for p in profiles.values()
                    for env in [p['credential_env'],
                                *p.get('credential_headers', {}).values(),
                                *([p['credential_env'] + '_EXPIRES_AT']
                                  if p['credential_kind'] == 'session-token' else [])]]
    if len(set(environments)) != len(environments):
        raise ValueError('Provider credentials must use distinct environment names.')
    return profiles


PROFILES = load_profiles()


def upstream_model(provider, model):
    profile = PROFILES[provider]
    if profile['models']:
        if model not in profile['models']:
            raise ValueError('Model is not mapped by the trusted provider profile.')
        return profile['models'][model]['upstream']
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9._:-]{1,120}', model):
        raise ValueError('Use the direct provider model ID without a vendor prefix.')
    return model
