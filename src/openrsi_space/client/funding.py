"""Early allowance feedback; the server's atomic admission remains authoritative."""
from decimal import Decimal, InvalidOperation
import json
import sys

from openrsi_space.common import OpenRSIError
from . import transport
from .local_check import pending_request


def amount(value):
    if type(value) not in (int, float):
        raise ValueError('Invalid allowance amount')
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError('Invalid allowance amount')
    return result


def dollars(value):
    return '$' + format(value, 'f')


def preflight(client, body):
    requested = Decimal(str(body['evaluation']['max_model_credits']))
    if requested < 1:
        raise OpenRSIError('Budget too low. Funded remote runs require --budget of at least $1. '
                           'Actual spending may be lower. No local evidence was uploaded or remote evaluation submitted.')
    # An uncertain prior POST may already hold this budget. Never block its
    # idempotent recovery because that hold lowered the reported availability.
    if pending_request(client.state, body, client.base) is not None:
        print('Resuming a saved request; the server will reconcile its existing funding reservation.',
              file=sys.stderr, flush=True)
        return
    try:
        raw = transport.solver_fetch(client.base, '/funding', client.bearer)
    except (OpenRSIError, OSError) as error:
        raise OpenRSIError(
            'Could not check your remote funding allowance. Run openrsi-space remote funding '
            'and retry when available. No local evidence was uploaded or remote evaluation submitted.'
        ) from error
    try:
        status = json.loads(raw)
        if not isinstance(status, dict) or status.get('mode') != 'platform' or type(status.get('halted')) is not bool:
            raise ValueError('Invalid funding response')
        if status['halted']:
            raise OpenRSIError('Platform funding is temporarily paused. No local evidence was uploaded '
                               'or remote evaluation submitted; retry when funding resumes.')
        allowance = status.get('allowance')
        if not isinstance(allowance, dict) or allowance.get('unit') != 'usd_equivalent':
            raise ValueError('Missing account allowance')
        remaining = amount(allowance.get('remaining'))
    except OpenRSIError:
        raise
    except (ValueError, TypeError, InvalidOperation):
        raise OpenRSIError('The server did not provide a valid account funding allowance. '
                           'Run openrsi-space remote funding or contact the operator. '
                           'No local evidence was uploaded or remote evaluation submitted.') from None
    if requested > remaining:
        raise OpenRSIError(
            f'Requested remote budget {dollars(requested)} exceeds your available allowance '
            f'of {dollars(remaining)} (after spending and outstanding reservations). '
            'Lower --budget, wait for allowance to become available, or contact the operator. '
            'Run openrsi-space remote funding for details. '
            'No local evidence was uploaded or remote evaluation submitted.')
    print(f'Funding check: requested {dollars(requested)}; available {dollars(remaining)}. '
          'The server reserves funds at admission; other eligibility and capacity limits still apply.',
          file=sys.stderr, flush=True)
