"""Fetch the CLI's tested runtime, without modifying user checkouts or old runs."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from openrsi_space.common import OpenRSIError


REPOSITORY = 'https://github.com/Layr-Labs/dungeness.git'
# Release pin, shared by all supported problems. Update only after compatibility tests.
REVISION = 'dbe7ee52974d25ddb109b5759491086d22bcf8f9'


def _git(root, *args):
    try:
        result = subprocess.run(
            ['git', '-C', str(root), *args], capture_output=True, text=True,
            timeout=180, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise OpenRSIError('Cannot prepare managed Dungeness. Check Git and network access, then retry; '
                           'no model calls were started by runtime preparation.') from error
    if result.returncode:
        # Git diagnostics may include credentials from local URL rewriting; do not echo them.
        raise OpenRSIError('Cannot prepare managed Dungeness. Check Git/network access and cache permissions, '
                           'then retry, or supply a clean compatible checkout with --dungeness PATH.')
    return result.stdout.strip()


def _validate(root):
    if (not (root / 'dungeness').is_file()
            or _git(root, 'rev-parse', 'HEAD') != REVISION
            or _git(root, 'status', '--porcelain', '--untracked-files=all')):
        raise OpenRSIError(f'Managed Dungeness cache is incomplete or modified: {root}. '
                           'Move that cache directory aside and retry, or use --dungeness PATH. '
                           'No older runtime was selected.')


@contextmanager
def _locked(path):
    with path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def resolve(override=None):
    """An explicit checkout wins; otherwise reuse or atomically install the pin."""
    if override is not None:
        return Path(override).expanduser().resolve()
    cache = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache').expanduser()
    parent = cache / 'openrsi-space' / 'runtimes' / 'dungeness'
    target = parent / REVISION
    try:
        parent.mkdir(parents=True, exist_ok=True)
        with _locked(parent / f'{REVISION}.lock'):
            if target.exists():
                _validate(target)
                return target
            print(f'Preparing managed Dungeness {REVISION[:12]} (no model calls)…',
                  file=sys.stderr, flush=True)
            with tempfile.TemporaryDirectory(prefix='.download-', dir=parent) as temporary:
                root = Path(temporary) / 'checkout'
                root.mkdir()
                _git(root, 'init', '--quiet')
                _git(root, 'fetch', '--quiet', '--depth=1', REPOSITORY, REVISION)
                _git(root, 'checkout', '--quiet', '--detach', 'FETCH_HEAD')
                _validate(root)
                root.rename(target)
        return target
    except OSError as error:
        raise OpenRSIError(f'Cannot use Dungeness cache at {parent}. Check cache permissions and disk space, '
                           'then retry, or use --dungeness PATH.') from error
