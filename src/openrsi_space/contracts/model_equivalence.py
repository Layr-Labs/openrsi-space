"""Backward-compatible evidence contract, derived from the shared model registry."""
from .model_registry import MODELS, REGISTRY_VERSION, model_binding

POLICY = 'openrsi-model-equivalence-v1'
# Preserve imports used by existing clients and tests; identities live only in MODELS.
GROUPS = tuple((m.canonical_id, m.local_routes) for m in MODELS)
ALIASES = {pair: ('openrouter', remote) for remote, pairs in GROUPS for pair in pairs}


def public_policy():
    return {'policy': POLICY, 'registry_version': REGISTRY_VERSION,
            'same_reasoning_effort_required': True,
            'equivalences': [{'remote': {'provider': 'openrouter', 'name': remote},
                              'local': [{'provider': p, 'name': n} for p, n in pairs]}
                             for remote, pairs in GROUPS]}
