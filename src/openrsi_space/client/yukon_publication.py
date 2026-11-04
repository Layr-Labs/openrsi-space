"""Client-owned publication intent and recovery; no key leaves local login storage at rest."""
import base64
import json
import time
from pathlib import Path

from openrsi_space.common import OpenRSIError, read_json
from openrsi_space.contracts.results import digest, evaluation_id
from openrsi_space.contracts.yukon_publication import PROTOCOL, metadata
from . import transport
from .state import request_lock, export_private_json
from openrsi_space.integrations.yukon import publication_transport as yukon
from openrsi_space.integrations.yukon.submission import bind_job, require_current_board
from openrsi_space.contracts.results import judgment, verification_reference
from openrsi_space.compatibility import SESSION_PROTOCOL


def options(args, *, saved=None):
    supplied = any(getattr(args, name, None) for name in (
        'note_file', 'publication_title', 'benchmark', 'dependencies_file', 'no_dependencies'))
    if not args.publish_to_yukon:
        if supplied:
            raise OpenRSIError('Publication options require --publish-to-yukon.')
        return None
    if saved is not None and not supplied:
        return saved['metadata']
    if not args.note_file or bool(args.dependencies_file) == bool(args.no_dependencies):
        raise OpenRSIError('--publish-to-yukon requires --note-file and either --no-dependencies or --dependencies-file.')
    from openrsi_space.integrations.yukon.submission import local_benchmark
    board = args.benchmark or local_benchmark(Path.cwd())
    if not board:
        raise OpenRSIError('Supply --benchmark with the Yukon benchmark UUID, or use a Yukon checkout.')
    title = args.publication_title
    if title is None and getattr(args, 'package', None):
        manifest = Path(args.package) / 'harness.json'
        title = read_json(manifest).get('title') if manifest.is_file() else None
    if not title:
        raise OpenRSIError('Supply --publication-title for this publication.')
    value = {'benchmark_id': board, 'harness': title,
             'note': Path(args.note_file).read_text(),
             'dependencies': read_json(Path(args.dependencies_file)) if args.dependencies_file else []}
    return metadata(value)


def intent_path(client, request):
    # Bound to evaluator and operation, not the current working directory.
    return client.state / 'remote/publications' / (digest({'base': client.base, 'request_id': request['request_id']}) + '.json')


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.parent.chmod(0o700)
    export_private_json(path, value)


def key(client):
    if not client.bearer.startswith('ykn_'):
        raise OpenRSIError('Yukon publication requires your Yukon login, not an OpenRSI session token.')
    return client.bearer


def prepare(client, request, info):
    """Freeze consent locally before admission. Only authenticated reads occur here."""
    info = metadata(info)
    require_current_board(info['benchmark_id'])
    origin, token = yukon.api_origin(), key(client)
    if token in json.dumps(info):
        raise OpenRSIError('Remove your Yukon key from the public publication metadata.')
    owner = evaluation_id(yukon.request(origin, '/api/me', token)['account']['id'])
    login = json.loads(transport.fetch(client.base + '/auth/yukon', token,
                                      document={'protocol': SESSION_PROTOCOL}, limit=16 * 1024))
    if login.get('owner_id') != owner or login.get('protocol') != SESSION_PROTOCOL:
        raise OpenRSIError('Yukon login and evaluator account do not match; check the selected API environments.')
    board = yukon.request(origin, '/api/benchmarks/' + info['benchmark_id'], token)['benchmark']
    if (board.get('id') != info['benchmark_id'] or board.get('status') != 'open'
            or board.get('mode') != 'pareto' or board.get('editablePaths') != ['submission/verification.json']):
        raise OpenRSIError('Automatic publication requires an open receipt-only Yukon board.')
    path = intent_path(client, request)
    consent = {'protocol': PROTOCOL, 'request_id': request['request_id'], 'request_digest': digest(request),
               'owner_id': owner, 'yukon_api': origin, 'metadata': info}
    with request_lock(path):
        if path.exists():
            previous = read_json(path)
            if any(previous.get(k) != v for k, v in consent.items()):
                raise OpenRSIError('Restore the authorized publication metadata, account and API; the saved intent is immutable.')
        else:
            save(path, {**consent, 'state': 'pending', 'submission_id': None, 'job_id': None, 'error_code': None})


def record(client, identity):
    session = client.session(evaluation_id(identity))
    path = intent_path(client, session['request'])
    if not path.is_file():
        return path, session, None
    value = read_json(path)
    if (value.get('protocol') != PROTOCOL or value.get('request_id') != session['request']['request_id']
            or value.get('request_digest') != digest(session['request'])):
        raise OpenRSIError('Publication intent does not match this evaluation; restore the original local state.')
    metadata(value['metadata'])
    return path, session, value


def projection(identity, value):
    result = {'protocol': PROTOCOL, 'evaluation_id': identity, 'state': 'not_requested'}
    if value:
        result.update(state=value['state'], benchmark_id=value['metadata']['benchmark_id'],
                      submission_id=value['submission_id'], job_id=value['job_id'], error_code=value['error_code'])
        if value['state'] == 'not_eligible':
            result['next_command'] = f'openrsi-space remote diagnostics {identity}'
        elif value['state'] in {'needs_authentication', 'retryable_failure'}:
            result['next_command'] = f'openrsi-space remote publication {identity} --retry'
        elif value['state'] != 'published':
            result['next_command'] = f'openrsi-space remote wait {identity}'
    return result


def owner(client, value):
    # A new login must not silently publish the prior user's receipt.
    if yukon.api_origin() != value['yukon_api']:
        raise OpenRSIError('Restore the Yukon API selected when you authorized publication.')
    token = key(client)
    if yukon.request(value['yukon_api'], '/api/me', token)['account']['id'] != value['owner_id']:
        raise yukon.PublicationError(401)
    return token


def check_submission(value, submission):
    if (submission.get('benchmarkId') != value['metadata']['benchmark_id']
            or submission.get('solverAccountId') != value['owner_id']
            or (value['submission_id'] is not None and submission.get('id') != value['submission_id'])):
        raise OpenRSIError('Yukon returned a different publication; retained result is unchanged.')
    return evaluation_id(submission['id'])


def publish(client, identity, *, wait=True):
    """Use the original receipt only. Never submit or restart research."""
    path, session, value = record(client, identity)
    if value is None:
        return projection(identity, None)
    with request_lock(path):
        # Another client may have finished between the initial read and lock.
        _, session, value = record(client, identity)
        if value['state'] in {'published', 'not_eligible'}:
            return projection(identity, value)
        try:
            token = owner(client, value)
            result = client.status(identity)  # Existing owner authentication and receipt bindings.
            if result['status'] not in {'completed', 'failed', 'cancelled'}:
                return projection(identity, value)
            if result['status'] != 'completed' or judgment(result, session['request']).get('valid') is not True:
                value.update(state='not_eligible', error_code='evaluation_not_verified')
                save(path, value)
                return projection(identity, value)
            reference = verification_reference(result, session['request'])
            if 'reference' in value and reference != value['reference']:
                raise OpenRSIError('Verified receipt changed; publication stopped.')
            if 'reference' not in value:
                value.update(reference=reference, archive_base64=base64.b64encode(yukon.archive(reference)).decode())
                save(path, value)  # Freeze bytes before the first possibly ambiguous write.
            info = value['metadata']
            model = session['request']['evaluation']['model']
            note = f"Model: {model['provider']}/{model['name']}\nHarness: {info['harness']}\n\n{info['note']}"
            origin = value['yukon_api']
            if value['submission_id'] is None:
                packed = base64.b64decode(value['archive_base64'], validate=True)
                if packed != yukon.archive(reference):
                    raise OpenRSIError('Saved upload differs from the verified receipt-only archive.')
                data, content_type = yukon.multipart(packed, note, info['dependencies'])
                value.update(state='submitting', error_code=None)
                save(path, value)
                response = yukon.request(origin, '/api/benchmarks/' + info['benchmark_id'] + '/submissions', token,
                    payload=data, content_type=content_type, idempotency='openrsi-' + identity)
                value.update(submission_id=check_submission(value, response['submission']), state='awaiting_yukon')
                save(path, value)
                if response.get('job') is not None:
                    value['job_id'] = evaluation_id(response['job']['id'])
                    save(path, value)
            if value['job_id'] is None:
                response = yukon.request(origin, '/api/submissions/' + value['submission_id'] + '/publication-job', token)
                value['job_id'] = evaluation_id(response['job']['id'])
                save(path, value)
            binding = bind_job(Path.cwd(), value['job_id'], info['benchmark_id'], reference=reference,
                               bearer=token, base=client.base)
            if binding['submission_id'] != value['submission_id']:
                raise OpenRSIError('Yukon execution binding names a different submission.')
            value.update(state='awaiting_yukon', error_code=None)
            save(path, value)
            deadline = time.monotonic() + (300 if wait else 0)
            while True:
                submission = yukon.request(origin, '/api/submissions/' + value['submission_id'], token)['submission']
                check_submission(value, submission)
                if submission.get('status') == 'accepted':
                    value.update(state='published', error_code=None)
                elif submission.get('status') in {'failed', 'rejected', 'cancelled'}:
                    value.update(state='retryable_failure', error_code='yukon_publication_failed')
                save(path, value)
                if value['state'] != 'awaiting_yukon' or time.monotonic() >= deadline:
                    break
                time.sleep(5)
        except (yukon.PublicationError, transport.HTTPFailure) as error:
            auth = error.status in {401, 403}
            value.update(state='needs_authentication' if auth else 'retryable_failure',
                         error_code='publication_authentication_required' if auth else 'publication_unavailable')
            save(path, value)
        except (OpenRSIError, ValueError, KeyError, TypeError):
            value.update(state='retryable_failure', error_code='publication_binding_or_metadata_mismatch')
            save(path, value)
        return projection(identity, value)


def status(client, identity, *, retry=False):
    if retry:
        return publish(client, identity)
    _, _, value = record(client, identity)
    # Reading status does not upload anything or authorize a new publication.
    return projection(identity, value)


def summary(client, identity):
    value = status(client, identity)
    return {} if value['state'] == 'not_requested' else {'publication': value}
