"""Exact model identities shared by setup, evidence matching and funding policy.

Canonical IDs use the existing OpenRouter spelling to preserve stored bindings.
This registry does not grant provider access or translate API protocols.
"""
from copy import deepcopy
from dataclasses import dataclass

REGISTRY_VERSION = 'openrsi-model-registry-20261119'


@dataclass(frozen=True)
class Model:
    canonical_id: str
    local_routes: tuple[tuple[str, str], ...]
    # New identities carry pinned reference rates here. Existing schedule entries
    # remain unchanged, including their historical comparison rates.
    reference_rates: dict | None = None


MODELS = (
    Model('openai/gpt-6-astra', (('openai-chatgpt', 'gpt-6-astra'), ('openai', 'gpt-6-astra'))),
    Model('openai/gpt-6-sol', (('openai-chatgpt', 'gpt-6-sol'), ('openai', 'gpt-6-sol'))),
    Model('openai/gpt-5.6-sol', (('openai-chatgpt', 'gpt-5.6-sol'), ('openai', 'gpt-5.6-sol'))),
    Model('anthropic/claude-opus-5', (('claude-subscription', 'claude-opus-5'), ('anthropic', 'claude-opus-5'))),
    Model('anthropic/claude-opus-5.5', (('claude-subscription', 'claude-opus-5-5'), ('anthropic', 'claude-opus-5-5'))),
    # Exact IDs and all cache/context tiers checked 2026-11-12:
    # https://platform.claude.com/docs/en/models/sonnet-5-5/overview
    # https://platform.claude.com/docs/en/models/haiku-5-5/overview
    Model('anthropic/claude-sonnet-5.5', (('claude-subscription', 'claude-sonnet-5-5'), ('anthropic', 'claude-sonnet-5-5')),
          dict(text_only=True, input_per_mtok=2.0, output_per_mtok=10.0, cached_read_per_mtok=0.10,
               cache_write_per_mtok=2.5, cache_write_1h_per_mtok=4.0)),
    Model('anthropic/claude-haiku-5.5', (('claude-subscription', 'claude-haiku-5-5'), ('anthropic', 'claude-haiku-5-5')),
          dict(text_only=True, input_per_mtok=0.10, output_per_mtok=0.50, cached_read_per_mtok=0.01,
               cache_write_per_mtok=0.125, cache_write_1h_per_mtok=0.20,
               long_context=dict(threshold_input_tokens=100000, input_per_mtok=0.50,
                                 output_per_mtok=2.50, cached_read_per_mtok=0.05,
                                 cache_write_per_mtok=0.625, cache_write_1h_per_mtok=1.0))),
    # GPT Standard text rates from Dungeness ba386048 (2026-11-19).
    Model('openai/gpt-6.2-astra', (('openai-chatgpt', 'gpt-6.2-astra'), ('openai', 'gpt-6.2-astra')),
          {'text_only': True, 'input_per_mtok': 8, 'cached_read_per_mtok': 0.4, 'cache_write_per_mtok': 10.0, 'output_per_mtok': 40, 'long_context': {'threshold_input_tokens': 272000, 'input_per_mtok': 16, 'cached_read_per_mtok': 0.8, 'cache_write_per_mtok': 20.0, 'output_per_mtok': 60.0}}),
    Model('openai/gpt-6.2-sol', (('openai-chatgpt', 'gpt-6.2-sol'), ('openai', 'gpt-6.2-sol')),
          {'text_only': True, 'input_per_mtok': 2, 'cached_read_per_mtok': 0.1, 'cache_write_per_mtok': 2.5, 'output_per_mtok': 10, 'long_context': {'threshold_input_tokens': 272000, 'input_per_mtok': 4, 'cached_read_per_mtok': 0.2, 'cache_write_per_mtok': 5.0, 'output_per_mtok': 15.0}}),
    Model('openai/gpt-6.1-sol', (('openai-chatgpt', 'gpt-6.1-sol'), ('openai', 'gpt-6.1-sol')),
          {'text_only': True, 'input_per_mtok': 2, 'cached_read_per_mtok': 0.1, 'cache_write_per_mtok': 2.5, 'output_per_mtok': 10, 'long_context': {'threshold_input_tokens': 272000, 'input_per_mtok': 4, 'cached_read_per_mtok': 0.2, 'cache_write_per_mtok': 5.0, 'output_per_mtok': 15.0}}),
    Model('openai/gpt-6.1-terra', (('openai-chatgpt', 'gpt-6.1-terra'), ('openai', 'gpt-6.1-terra')),
          {'input_per_mtok': 1.0, 'cached_read_per_mtok': 0.05, 'cache_write_per_mtok': 1.25, 'output_per_mtok': 5.0, 'text_only': True, 'long_context': {'threshold_input_tokens': 272000, 'input_per_mtok': 2.0, 'cached_read_per_mtok': 0.1, 'cache_write_per_mtok': 2.5, 'output_per_mtok': 7.5}}),
    Model('openai/gpt-6-luna', (('openai-chatgpt', 'gpt-6-luna'), ('openai', 'gpt-6-luna')),
          {'text_only': True, 'input_per_mtok': 0.1, 'cached_read_per_mtok': 0.01, 'cache_write_per_mtok': 0.125, 'output_per_mtok': 0.5, 'long_context': {'threshold_input_tokens': 272000, 'input_per_mtok': 0.2, 'cached_read_per_mtok': 0.02, 'cache_write_per_mtok': 0.25, 'output_per_mtok': 0.75}}),
    Model('openai/gpt-5.6-terra', (('openai-chatgpt', 'gpt-5.6-terra'), ('openai', 'gpt-5.6-terra')),
          {'input_per_mtok': 2.0, 'cached_read_per_mtok': 0.2, 'cache_write_per_mtok': 2.5, 'output_per_mtok': 12.0, 'text_only': True, 'long_context': {'threshold_input_tokens': 272000, 'input_per_mtok': 4.0, 'cached_read_per_mtok': 0.4, 'cache_write_per_mtok': 5.0, 'output_per_mtok': 18.0}}),
    Model('openai/gpt-5.6-luna', (('openai-chatgpt', 'gpt-5.6-luna'), ('openai', 'gpt-5.6-luna')),
          {'text_only': True, 'input_per_mtok': 0.2, 'cached_read_per_mtok': 0.02, 'cache_write_per_mtok': 0.25, 'output_per_mtok': 1.2, 'long_context': {'threshold_input_tokens': 272000, 'input_per_mtok': 0.4, 'cached_read_per_mtok': 0.04, 'cache_write_per_mtok': 0.5, 'output_per_mtok': 1.8}}),
    # Anthropic model IDs and cache-duration rates checked 2026-11-12:
    # https://platform.claude.com/docs/en/models/fable-5/overview
    # https://platform.claude.com/docs/en/models/fable-5-1/overview
    # https://platform.claude.com/docs/en/models/fable-5-2/overview
    Model('anthropic/claude-fable-5', (('claude-subscription', 'claude-fable-5'), ('anthropic', 'claude-fable-5')),
          dict(text_only=True, input_per_mtok=10.0, output_per_mtok=50.0, cached_read_per_mtok=1.0,
               cache_write_per_mtok=12.5, cache_write_1h_per_mtok=20.0)),
    Model('anthropic/claude-fable-5.1', (('claude-subscription', 'claude-fable-5-1'), ('anthropic', 'claude-fable-5-1')),
          dict(text_only=True, input_per_mtok=10.0, output_per_mtok=50.0, cached_read_per_mtok=0.25,
               cache_write_per_mtok=12.5, cache_write_1h_per_mtok=20.0)),
    Model('anthropic/claude-fable-5.2', (('claude-subscription', 'claude-fable-5-2'), ('anthropic', 'claude-fable-5-2')),
          dict(text_only=True, input_per_mtok=8.0, output_per_mtok=40.0, cached_read_per_mtok=0.20,
               cache_write_per_mtok=10.0, cache_write_1h_per_mtok=16.0)),
    Model('x-ai/grok-4.7', (('grok-subscription', 'grok-4.7'),)),
    Model('minimax/minimax-m3', (('minimax-subscription', 'MiniMax-M3'),)),
    Model('minimax/minimax-m3.1-flash', (('minimax-subscription', 'MiniMax-M3.1-Flash'),)),
)
BY_ROUTE = {route: model for model in MODELS
            for route in (('openrouter', model.canonical_id), *model.local_routes)}


def remote_model(model):
    """Return an exact funded route, or None for an unsupported provider pair."""
    identity = BY_ROUTE.get((model['provider'], model['name']))
    if identity:
        return {**model, 'provider': 'openrouter', 'name': identity.canonical_id}
    if model['provider'] == 'openrouter':
        return dict(model)  # Exact same-provider identity requires no equivalence.
    return None


def model_binding(models):
    return sorted((mapped['provider'], mapped['name'], mapped.get('reasoning_effort') or '')
                  for model in models for mapped in (remote_model(model) or model,))


def reference_pricing(schedule):
    """Fill missing registered routes; never rewrite an existing rate entry."""
    result = deepcopy(schedule)
    entries = result['entries']
    existing = {(e['provider'], name) for e in entries for name in e['request_models']}
    for model in MODELS:
        remote = next((e for e in entries if e['provider'] == 'openrouter'
                       and model.canonical_id in e['request_models']), None)
        rates = model.reference_rates or remote
        if rates is None:
            raise ValueError(f'Model registry lacks reference pricing: {model.canonical_id}')
        for provider, name in (('openrouter', model.canonical_id), *model.local_routes):
            if (provider, name) in existing:
                continue
            entry = deepcopy(rates)
            entry.update(provider=provider, upstream_id=model.canonical_id, request_models=[name])
            entries.append(entry)
            existing.add((provider, name))
    return result


def supports_no_reasoning(model):
    """Only explicitly qualified routes may request disabled reasoning."""
    mapped = remote_model(model)
    return mapped is not None and mapped['provider'] == 'openrouter' and mapped['name'] in {
        'openai/gpt-6.1-terra', 'openai/gpt-6-sol', 'openai/gpt-6-luna',
        'openai/gpt-5.6-sol', 'openai/gpt-5.6-terra', 'openai/gpt-5.6-luna',
    }
