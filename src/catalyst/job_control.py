"""Cooperative cancellation at trusted process and state-transition boundaries."""
from contextlib import contextmanager
from contextvars import ContextVar

from catalyst.common import CatalystError


class JobCancelled(CatalystError):
    pass


class JobNeedsCredentials(CatalystError):
    pass


_check = ContextVar("catalyst_job_cancel_check", default=lambda: None)


def check_cancelled():
    _check.get()()


@contextmanager
def cancellation_scope(check):
    token = _check.set(check)
    try:
        check_cancelled()
        yield
        check_cancelled()
    finally:
        _check.reset(token)


import os

def signal_group(group, sig):
    try:
        os.killpg(group, sig)
    except ProcessLookupError:
        pass

def group_exists(group):
    try:
        os.killpg(group, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Darwin may report EPERM briefly while an orphaned group exits.
        # A denied probe does not establish that the group has disappeared.
        return True
