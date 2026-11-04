"""Public metadata for an explicitly authorized Yukon publication."""
import re

from openrsi_space.common import OpenRSIError, canonical
from openrsi_space.protocol import identity

PROTOCOL = 'openrsi-yukon-publication-v1'


def metadata(value):
    if not isinstance(value, dict) or set(value) != {'benchmark_id', 'harness', 'note', 'dependencies'}:
        raise OpenRSIError('Publication requires a benchmark UUID, harness title, note and explicit dependencies.')
    identity(value['benchmark_id'])
    title, note, dependencies = value['harness'], value['note'], value['dependencies']
    if not isinstance(title, str) or not title.strip() or len(title) > 200 or any(ord(c) < 32 for c in title):
        raise OpenRSIError('Publication harness title must be one nonempty line of at most 200 characters.')
    if not isinstance(note, str) or not note.strip() or len(note.encode()) > 96 * 1024:
        raise OpenRSIError('Publication note must be nonempty and at most 96 KiB.')
    if not isinstance(dependencies, list) or len(dependencies) > 20 or len(canonical(dependencies)) > 64 * 1024:
        raise OpenRSIError('Publication dependencies must be a list of at most 20 declarations, under 64 KiB.')
    seen = set()
    for entry in dependencies:
        if not isinstance(entry, dict) or set(entry) not in (
                {'submissionId', 'rationale', 'evidence'}, {'submissionId', 'rationale', 'evidence', 'citations'}):
            raise OpenRSIError('Invalid publication dependency declaration.')
        sid = identity(entry['submissionId'])
        if sid in seen:
            raise OpenRSIError('Declare each publication dependency once.')
        seen.add(sid)
        for name, limit in [('rationale', 4000), ('evidence', 8000)]:
            if not isinstance(entry[name], str) or not entry[name].strip() or len(entry[name]) > limit:
                raise OpenRSIError('Invalid publication dependency text.')
        if 'citations' in entry:
            citations = entry['citations']
            if not isinstance(citations, list) or not 1 <= len(citations) <= 24:
                raise OpenRSIError('Invalid publication dependency citations.')
            for citation in citations:
                if not isinstance(citation, dict) or set(citation) != {
                        'submissionId', 'path', 'fileSha256', 'startLine', 'endLine'}:
                    raise OpenRSIError('Invalid publication dependency citation.')
                if citation['submissionId'] is not None:
                    identity(citation['submissionId'])
                if (not isinstance(citation['path'], str) or not 1 <= len(citation['path']) <= 1024
                        or not isinstance(citation['fileSha256'], str)
                        or not re.fullmatch('[a-f0-9]{64}', citation['fileSha256'])
                        or type(citation['startLine']) is not int or type(citation['endLine']) is not int
                        or not 1 <= citation['startLine'] <= citation['endLine']):
                    raise OpenRSIError('Invalid publication dependency citation location.')
    return value
