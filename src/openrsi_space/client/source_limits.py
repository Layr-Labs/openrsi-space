"""Public submission limits and local source measurement; no credentials or uploads."""
from openrsi_space.compatibility import SUBMISSION_POLICY_PROTOCOL
from io import BytesIO
import json
from zipfile import ZipFile

from openrsi_space.common import OpenRSIError
from . import transport

DEFAULT_EXPANDED_BYTES = 8 * 1024 * 1024


def measure(snapshot, archive):
    with ZipFile(BytesIO(archive)) as bundle:
        return {'expanded_source_bytes': sum(entry.file_size for entry in bundle.infolist()
                                            if entry.filename in snapshot['files']),
                'archive_bytes': len(archive), 'file_count': len(snapshot['files'])}


def check(size, expanded_limit, archive_limit):
    if size['expanded_source_bytes'] > expanded_limit:
        raise OpenRSIError(f"Expanded harness source is {size['expanded_source_bytes']:,} bytes; "
                            f"limit is {expanded_limit:,} bytes. Remove unused vendored modules, tests, examples "
                            "and assets while retaining runtime code and licenses. ZIP compression does not "
                            "change this limit. No source or model credential was uploaded.")
    if size['archive_bytes'] > archive_limit:
        raise OpenRSIError(f"Harness ZIP is {size['archive_bytes']:,} bytes; archive limit is "
                            f"{archive_limit:,} bytes. Reduce the submission package before uploading.")


def policy(base=None):
    base = base or transport.endpoint()
    raw = transport.fetch(base + '/public/submission-policy', None, limit=8192)
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get('protocol') != SUBMISSION_POLICY_PROTOCOL:
        raise OpenRSIError('Evaluator returned an unsupported submission policy.')
    for field in ('max_expanded_source_bytes', 'max_archive_bytes'):
        if type(value.get(field)) is not int or not 1 <= value[field] <= 512 * 1024 * 1024:
            raise OpenRSIError('Evaluator returned invalid source limits.')
    # Print only a fixed projection; never arbitrary server-returned prose.
    return {'protocol': value['protocol'], 'max_expanded_source_bytes': value['max_expanded_source_bytes'],
            'max_archive_bytes': value['max_archive_bytes']}
