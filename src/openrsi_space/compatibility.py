"""Read compatibility for existing evidence and deployed verifier contracts.

These exact identifiers are retained; replacing them would invalidate existing
source digests, hosted authentication or retained records. New package names,
commands, environment settings and documentation use OpenRSI.
"""
import os
from pathlib import Path

EVALUATION_PROTOCOL = 'catalyst-evaluation-v3'
DIAGNOSTICS_PROTOCOL = 'catalyst-diagnostics-v1'
FUNDING_PROTOCOL = 'catalyst-funding-policy-v1'
EVIDENCE_PROTOCOL = 'catalyst-local-evidence-v1'
SESSION_PROTOCOL = 'catalyst-yukon-session-v1'
ARTIFACT_PROTOCOL = 'catalyst-artifacts-v1'
CATALOG_PROTOCOL = 'catalyst-harness-catalog-v1'
BUILD_POLICY_PROTOCOL = 'catalyst-build-dependency-policy-v1'
SUBMISSION_POLICY_PROTOCOL = 'catalyst-submission-policy-v1'
MODEL_TOKEN_HEADER = 'X-Catalyst-Model-Token'
CORRELATION_HEADER = 'X-Catalyst-Correlation-ID'
EDGE_HEADER = 'X-Catalyst-Edge-ID'
OIDC_AUDIENCE = 'catalyst-evaluator'
SNAPSHOT_FILENAME = 'catalyst-snapshot.json'
RUNTIME_NAMESPACE = 'projects/catalyst'
PROBLEM_PREFIX = 'catalyst-'
PROBLEM_DIGEST_LABEL = 'catalyst_problem_set_digest'
LEGACY_INTERFACE = 'catalyst-exec-v1'
LEGACY_STATE = '.catalyst'


def environment(name, default=None):
    """Canonical settings win, including an explicitly empty setting."""
    if name in os.environ:
        return os.environ[name]
    legacy = "CATALYST_" + name.removeprefix("OPENRSI_")
    return os.environ.get(legacy, default)


def state_directory(root=None):
    root = Path('.') if root is None else Path(root)
    configured = environment('OPENRSI_STATE')
    if configured is not None:
        return Path(configured)
    current, previous = root / '.openrsi', root / LEGACY_STATE
    return previous if previous.is_dir() and not current.exists() else current


def image_source(labels):
    """Honor one source binding, preferring the new label when both exist."""
    return labels.get('openrsi.source', labels.get('catalyst.source'))


def image_runtime_root(build):
    return '/opt/catalyst' if build.get('interface') == LEGACY_INTERFACE else '/opt/openrsi'
