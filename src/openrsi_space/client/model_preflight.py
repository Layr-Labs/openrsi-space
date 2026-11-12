"""Credential-free funding compatibility check before local builds or inference."""
import json

from openrsi_space.common import OpenRSIError
from openrsi_space.compatibility import FUNDING_PROTOCOL
from openrsi_space.contracts.accounting import model_prices
from openrsi_space.contracts.model_registry import remote_model
from . import transport


def check(models, pricing):
    remotes = []
    for model in models:
        remote = remote_model(model)
        if remote is None:
            raise OpenRSIError(
                f"No supported remote equivalent for {model['provider']}/{model['name']}. "
                'Update the client or choose a supported model before testing. '
                'Use --local-only only for experiments without a remote eligibility check.')
        try:
            model_prices(model, pricing)
        except OpenRSIError:
            raise OpenRSIError('Selected local model has no reference pricing. Update the client '
                               'or supply a trusted --pricing schedule before testing.') from None
        remotes.append(remote)
    try:
        policy = json.loads(transport.fetch(transport.endpoint() + '/public/funding-policy',
                                           None, limit=65536, timeout=10))
        if not isinstance(policy, dict) or policy.get('protocol') != FUNDING_PROTOCOL:
            raise ValueError
        equivalences = policy['local_evidence_models']['equivalences']
        if not isinstance(equivalences, list):
            raise ValueError
        if policy.get('enabled') is not True or 'openrouter' not in policy.get('providers', []):
            raise OpenRSIError('Remote funding is unavailable. Retry later, or use --local-only '
                               'to test without checking remote eligibility.')
        for local, remote in zip(models, remotes):
            pair = {k: local[k] for k in ('provider', 'name')}
            target = {k: remote[k] for k in ('provider', 'name')}
            if pair != target and not any(g.get('remote') == target and pair in g.get('local', [])
                                          for g in equivalences if isinstance(g, dict)):
                raise OpenRSIError(
                    f"The evaluator does not currently support {local['provider']}/{local['name']} "
                    f"as evidence for {remote['name']}. No local run started. "
                    'Check remote funding-policy or use --local-only for an independent experiment.')
            if policy.get('model_selection') == 'restricted' and target not in policy.get('models', []):
                raise OpenRSIError('The evaluator does not fund the selected model. No local run started.')
    except OpenRSIError:
        raise
    except (ValueError, KeyError, TypeError):
        raise OpenRSIError('Cannot validate the evaluator model policy. No local run started. '
                           'Retry, or use --local-only for an independent experiment.') from None
    return remotes
