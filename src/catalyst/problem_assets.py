"""Install public, operator-owned problem assets into disposable runtimes.

The registry is part of the Catalyst distribution, never a submitted harness.
Only scaffold and verifier directories may be installed through this interface.
"""
import json
from pathlib import Path
import shutil

from .common import CatalystError, safe_relative

ROOT = Path(__file__).parent / 'problem-set'


def registered_assets():
    registry = json.loads((ROOT / 'runtime-assets.json').read_text())
    if registry.get('schema_version') != 1 or not isinstance(registry.get('assets'), dict):
        raise CatalystError('Invalid installed problem asset registry.')
    result = {}
    for destination, source in registry['assets'].items():
        safe_relative(destination)
        safe_relative(source)
        if len(Path(destination).parts) < 2 or Path(destination).parts[0] not in {'scaffolds', 'verifiers'}:
            raise CatalystError('Problem assets may only install scaffold or verifier directories.')
        folder = ROOT / source
        if (folder.is_symlink() or not folder.is_dir()
                or not folder.resolve().is_relative_to(ROOT.resolve())
                or any(path.is_symlink() for path in folder.rglob('*'))):
            raise CatalystError(f'Invalid installed problem asset directory: {source}')
        result[destination] = folder
    return result


def asset_path(runtime, relative):
    """Prefer the challenge-owned asset; retain operator-supplied generic assets."""
    safe_relative(relative)
    path = Path(relative)
    for destination, source in registered_assets().items():
        if path.is_relative_to(destination):
            return source / path.relative_to(destination)
    result = runtime / relative
    if result.is_symlink() or not result.resolve().is_relative_to(runtime.resolve()):
        raise CatalystError('Trusted runtime asset escapes the runtime.')
    return result


def install_assets(runtime, execution):
    references = [execution[key] for key in ('scaffold',) if key in execution]
    if execution.get('verifier'):
        references.append('verifiers/' + execution['verifier'])
    added = []
    for destination, source in registered_assets().items():
        if not any(Path(reference).is_relative_to(destination) for reference in references):
            continue
        target = runtime / destination
        if target.is_symlink() or not target.resolve().is_relative_to(runtime.resolve()):
            raise CatalystError('Problem asset destination escapes the disposable runtime.')
        if target.exists():
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
        added.append(destination)
    return added
