"""Compatibility facade; use contracts/* or client/* for new code."""
from ._compat import forward_module as _forward
from .contracts import evaluation as _evaluation, results as _results
from .client import configuration as _configuration, transport as _transport, state as _state, evaluations as _client

_forward(__name__, {
    "validate_evaluation_config": _evaluation,
    "validate_limits": _evaluation,
    "limits_within": _evaluation,
    "validate_model": _evaluation,
    "PROTOCOL": _results,
    "SCORING": _results,
    "VALIDITY": _results,
    "LEGACY_VALIDITY": _results,
    "PENDING": _results,
    "TERMINAL": _results,
    "digest": _results,
    "judge_input": _results,
    "bound_result": _results,
    "judgment": _results,
    "verification_reference": _results,
    "evaluation_id": _results,
    "evaluation_config": _configuration,
    "NoRedirect": _transport,
    "HTTPFailure": _transport,
    "fetch": _transport,
    "solver_fetch": _transport,
    "endpoint": _transport,
    "solver_token": _transport,
    "_solver_sessions": _transport,
    "urllib": _transport,
    "request_lock": _state,
    "private_json": _state,
    "RemoteClient": _client,
    "request_body": _client,
    "source_snapshot": _client,
    "MAX_SOURCE_BYTES": _client,
    "time": _client,
})
