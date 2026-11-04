"""Bounded Yukon HTTP and receipt-only uploads; no subprocess or credential storage."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import urllib.error
import urllib.parse
import urllib.request

from openrsi_space.common import OpenRSIError, canonical, read_json
from openrsi_space.client.transport import NoRedirect


class PublicationError(OpenRSIError):
    def __init__(self, status):
        self.status = status
        super().__init__('Yukon authentication is required.' if status in (401, 403)
                         else 'Yukon publication could not complete; retry the saved publication.')


def api_origin():
    root = Path(os.environ.get('YUKON_CONFIG_DIR', str(Path.home() / '.config')))
    path = root / 'yukon/config.json'
    if not path.is_file() and not os.environ.get('YUKON_CONFIG_DIR'):
        path = root / 'hilbert/config.json'
    config = read_json(path) if path.is_file() else {}
    value = os.environ.get('YUKON_API_URL') or os.environ.get('HILBERT_API_URL') or config.get('apiBaseUrl') or 'https://yukon-api-dev.fly.dev'
    parts = urllib.parse.urlsplit(value)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment or parts.path not in ('', '/')):
        raise OpenRSIError('Configure your Yukon CLI with a trusted HTTPS API origin.')
    return value.rstrip('/')


def request(origin, path, key, *, payload=None, content_type=None, idempotency=None):
    headers = {'Authorization': 'Bearer ' + key, 'Accept': 'application/json'}
    if content_type:
        headers['Content-Type'] = content_type
    if idempotency:
        headers['Idempotency-Key'] = idempotency
    req = urllib.request.Request(origin + path, data=payload, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as response:
            data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError
        return json.loads(data)
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        raise PublicationError(status) from None
    except (OSError, ValueError, OpenRSIError):
        raise PublicationError(503) from None


def archive(reference):
    content = canonical(reference)
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as tar:
        entry = tarfile.TarInfo('submission/verification.json')
        entry.size, entry.mode = len(content), 0o644
        tar.addfile(entry, io.BytesIO(content))
    return gzip.compress(stream.getvalue(), mtime=0)


def multipart(archive_bytes, note, dependencies):
    boundary = 'openrsi-' + hashlib.sha256(archive_bytes + note.encode() + canonical(dependencies)).hexdigest()
    chunks = []
    for name, data, filename in [('archive', archive_bytes, 'submission.tar.gz'),
                                  ('note', note.encode(), None),
                                  ('dependencies', canonical(dependencies), None)]:
        header = f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
        if filename:
            header += f'; filename="{filename}"\r\nContent-Type: application/gzip'
        chunks.extend([header.encode() + b'\r\n\r\n', data, b'\r\n'])
    chunks.append(f'--{boundary}--\r\n'.encode())
    return b''.join(chunks), 'multipart/form-data; boundary=' + boundary
