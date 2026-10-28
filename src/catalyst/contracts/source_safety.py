"""Early local packaging guard; authoritative content screening stays on the verifier."""
from catalyst.common import CatalystError

PRIVATE_NAMES = frozenset({
    '.aws', '.ssh', '.codex', '.claude', '.azure', '.kube', '.netrc',
    '.git-credentials', '.npmrc', '.pypirc', 'auth.json', 'credentials.json',
    'application_default_credentials.json', 'token.txt', 'tokens.json',
    'id_rsa', 'id_ed25519',
})


def check_source_path(relative):
    # Report only fixed labels, never arbitrary paths or their contents: a path
    # itself can contain a secret. Check before opening the file.
    suspicious = next((part.lower() for part in relative.parts if part.lower() in PRIVATE_NAMES), None)
    if suspicious:
        raise CatalystError(
            f'Harness packaging stopped: credential-like file or directory ({suspicious}). '
            'Keep login files and model credentials outside the harness source; '
            'supply model access through the credential options. No archive was created. '
            'If this is ordinary source code, give it an unambiguous source filename. '
            'The verifier also screens file contents; renaming a credential does not make it safe.')
