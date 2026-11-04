"""Cooperative cancellation at trusted process and state-transition boundaries."""
from contextlib import contextmanager
from contextvars import ContextVar

from openrsi_space.common import OpenRSIError


class JobCancelled(OpenRSIError):
    pass


_check = ContextVar("openrsi_job_cancel_check", default=lambda: None)


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
