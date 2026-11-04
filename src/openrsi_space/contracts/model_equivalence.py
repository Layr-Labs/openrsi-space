"""Exact, versioned cross-provider identities for local evidence matching.

This is an eligibility policy, not an API translator. Preserve the actual local
provider in evidence. Unknown identities still require exact provider matching.
"""

POLICY = 'openrsi-model-equivalence-v1'
GROUPS = (
    ('openai/gpt-6-astra', (('openai-chatgpt', 'gpt-6-astra'), ('openai', 'gpt-6-astra'))),
    ('openai/gpt-6-sol', (('openai-chatgpt', 'gpt-6-sol'), ('openai', 'gpt-6-sol'))),
    ('openai/gpt-5.6-sol', (('openai-chatgpt', 'gpt-5.6-sol'), ('openai', 'gpt-5.6-sol'))),
    ('anthropic/claude-opus-5', (('claude-subscription', 'claude-opus-5'), ('anthropic', 'claude-opus-5'))),
    ('anthropic/claude-opus-5.5', (('claude-subscription', 'claude-opus-5-5'), ('anthropic', 'claude-opus-5-5'))),
    ('x-ai/grok-4.7', (('grok-subscription', 'grok-4.7'),)),
    ('minimax/minimax-m3', (('minimax-subscription', 'MiniMax-M3'),)),
    ('minimax/minimax-m3.1-flash', (('minimax-subscription', 'MiniMax-M3.1-Flash'),)),
)
ALIASES = {pair: ('openrouter', remote) for remote, pairs in GROUPS for pair in pairs}


def model_binding(models):
    return sorted((*ALIASES.get((m['provider'], m['name']), (m['provider'], m['name'])),
                   m.get('reasoning_effort') or '') for m in models)


def public_policy():
    return {'policy': POLICY, 'same_reasoning_effort_required': True,
            'equivalences': [{'remote': {'provider': 'openrouter', 'name': remote},
                              'local': [{'provider': p, 'name': n} for p, n in pairs]}
                             for remote, pairs in GROUPS]}
