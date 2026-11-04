"""Descriptor-based source capture; never reopen checked entries by pathname."""
import os
from pathlib import Path, PurePosixPath
import stat

from .common import OpenRSIError, IGNORED, MAX_BUNDLE_BYTES, RESERVED


def identity(info):
    return info.st_dev, info.st_ino, info.st_mode


def version(info):
    return identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns


def capture(path, *, exclude=frozenset(), harness=False):
    if not all(hasattr(os, flag) for flag in ('O_NOFOLLOW', 'O_DIRECTORY', 'O_NONBLOCK')):
        raise OpenRSIError('Secure source capture requires a POSIX filesystem with no-follow descriptor support.')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
    opened = []
    files = {}
    size = 0
    try:
        # Anchor every path component. A replaced ancestor must not redirect us.
        absolute = Path(os.path.abspath(path))
        fd = os.open(absolute.anchor, flags | os.O_DIRECTORY)
        opened.append(fd)
        anchors = []
        for component in absolute.parts[1:]:
            parent = fd
            fd = os.open(component, flags | os.O_DIRECTORY, dir_fd=parent)
            opened.append(fd)
            anchors.append((parent, component, identity(os.fstat(fd))))
        root = fd
        harness = harness or 'harness.json' in os.listdir(root)

        def walk(directory, prefix):
            nonlocal size
            before = os.fstat(directory)
            for name in sorted(os.listdir(directory)):
                relative = PurePosixPath(prefix, name)
                if (relative.as_posix() in exclude or name in IGNORED or name.startswith('.env')
                        or name == RESERVED):
                    continue
                if harness:
                    from .contracts.source_safety import check_source_path
                    check_source_path(relative)
                checked = os.stat(name, dir_fd=directory, follow_symlinks=False)
                if stat.S_ISLNK(checked.st_mode):
                    raise OpenRSIError(f'Package symlinks are unsupported: {relative}')
                if not (stat.S_ISDIR(checked.st_mode) or stat.S_ISREG(checked.st_mode)):
                    raise OpenRSIError(f'Package special files are unsupported: {relative}')
                entry = os.open(name, flags | os.O_NONBLOCK |
                                (os.O_DIRECTORY if stat.S_ISDIR(checked.st_mode) else 0), dir_fd=directory)
                try:
                    actual = os.fstat(entry)
                    if version(actual) != version(checked):
                        raise OpenRSIError(f'Source changed during capture: {relative}')
                    if stat.S_ISDIR(actual.st_mode):
                        walk(entry, relative)
                    else:
                        if len(files) >= 2000 or actual.st_size > MAX_BUNDLE_BYTES - size:
                            raise OpenRSIError('Source exceeds the bundle size or file-count limit.')
                        data = bytearray()
                        while len(data) <= MAX_BUNDLE_BYTES - size:
                            chunk = os.read(entry, min(65536, MAX_BUNDLE_BYTES - size - len(data) + 1))
                            if not chunk:
                                break
                            data.extend(chunk)
                        if len(data) > MAX_BUNDLE_BYTES - size:
                            raise OpenRSIError('Source exceeds the bundle size limit.')
                        if version(os.fstat(entry)) != version(actual):
                            raise OpenRSIError(f'Source changed during capture: {relative}')
                        files[relative.as_posix()] = bytes(data)
                        size += len(data)
                    # Check the directory entry still names the opened object.
                    if version(os.stat(name, dir_fd=directory, follow_symlinks=False)) != version(actual):
                        raise OpenRSIError(f'Source changed during capture: {relative}')
                finally:
                    os.close(entry)
            if version(os.fstat(directory)) != version(before):
                raise OpenRSIError('Source directory changed during capture; stop writers and retry.')

        walk(root, '')
        for parent, name, expected in anchors:
            if identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != expected:
                raise OpenRSIError('Source directory identity changed during capture.')
        return files
    except OSError:
        # Do not include target paths, file contents, or untrusted exception text.
        raise OpenRSIError('Cannot safely snapshot source: a path changed, is unreadable, or contains a symlink. Stop writers and retry.') from None
    finally:
        for fd in reversed(opened):
            os.close(fd)
