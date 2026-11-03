"""Bounded HTTP, safe downloads and process-local Yukon login sessions."""
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from catalyst.common import CatalystError, canonical, read_json
from catalyst.contracts.results import evaluation_id

_solver_sessions = {}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CatalystError("Evaluator redirects are refused to protect authorization.")


def credential_url(url, *, model_access=False):
    """Validate before opening a connection or exchanging a solver login."""
    parts = urllib.parse.urlsplit(url)
    loopback = parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "::1"}
    if (not parts.hostname or parts.username or parts.password or parts.fragment
            or (parts.scheme != "https" and not (loopback and not model_access))):
        raise CatalystError("Credentials require a trusted HTTPS evaluator endpoint; HTTP is only for local fixtures.")
    if model_access:
        route = parts.path.split("/")
        renewal = len(route) == 4 and route[:2] == ["", "evaluations"] and route[3] == "credentials"
        if renewal:
            evaluation_id(route[2])
        if parts.query or not (parts.path == "/evaluations" or renewal):
            raise CatalystError("Provider tokens require an HTTPS evaluation submission or credential-renewal endpoint.")


ADMISSION_FIELDS = {
    "authentication": {"authorization"},
    "framing": {"content_length", "content_type", "body"},
    "validation": {"request", "publication", "request_id", "protocol", "evidence_mode",
                   "problem_set", "pricing", "evaluation", "evaluation.schema_version",
                   "evaluation.limits", "evaluation.limits.max_seconds", "evaluation.limits.max_model_tokens",
                   "evaluation.model", "evaluation.model.reasoning_effort", "evaluation.max_model_credits", "judge", "context", "source",
                   "source.archive_base64", "source.digest", "source.execution", "source.publication", "source.expanded_bytes"},
    "authorization": {"evaluation"}, "credentials": {"model_access"},
    "creation": {"request_id", "local_evidence"}, "readiness": {"service"},
}
QUOTA_MESSAGES = {
    'account_concurrency': 'Your account has reached its active-run limit; wait for a run to finish or cancel it.',
    'global_capacity': 'All evaluation slots are occupied; retry after a run finishes.',
    'submission_rate_limit': 'Too many new submissions in the short submission window.',
    'funding_allowance_exhausted': 'Funded allowance is exhausted or reserved; wait for settlement or contact the operator. Amounts are in microcredits (1,000,000 = one normalized credit).',
    'daily_quota': 'The operator-configured daily evaluation quota is reached.',
}
ADMISSION_MESSAGES = {
    **QUOTA_MESSAGES,
    "funding_unavailable": "Platform funding is disabled or unavailable; contact the operator.",
    "funding_paused": "Platform funding is paused for reconciliation; contact the operator.",
    "funding_model_not_allowed": "Choose a model from /public/funding-policy.",
    "funding_provider_not_available": "Choose a funded provider from /public/funding-policy and declare your exact model. Matching local evidence and a valid pricing quote are required.",
    "funding_not_enrolled": "Your account is not enrolled for platform-funded inference.",
    "funding_identity_required": "Log in to Yukon and retry with your Yukon API key.",
    "funding_identity_conflict": "Account identity binding conflicts; contact the operator.",
    "local_evidence_insufficient_spend": "Recorded local spending is below the operator's evidence threshold; check remote funding-policy before spending more.",
    "local_evidence_required": "Provide --local-run PATH to a ended matching local Dungeness run.",
    "local_evidence_invalid": "Local evidence is incomplete or invalid. Retain complete request, response and settled accounting events from an ended local run.",
    "local_evidence_budget_cap_missing": "Update the OpenRSI client and re-export with --local-run PATH from the original local record containing its budget cap; a new run is not needed if that record has a sufficient cap.",
    "local_evidence_budget_cap_invalid": "The recorded local budget cap must be a positive finite number. Use an original valid local record; do not infer the cap from spending.",
    "local_evidence_budget_cap_insufficient": "Lower the remote budget or select a matching local run whose recorded cap covers it; actual spending may be lower. No minimum-spend percentage applies.",
    "local_evidence_mismatch": "Local evidence must match the submitted source, problem, model and reasoning settings, using a supported provider equivalence.",
    "local_evidence_not_private": "Local evidence contains a recognized credential or uninspectable content. Check the reported event and rule before changing source or repeating a local run.",
    "local_evidence_capacity": "Private evidence storage is full; contact the operator or wait for upload expiry.",
    "local_evidence_rate_limit": "Too many evidence uploads; retry in an hour.",
    "local_evidence_too_large": "Local evidence exceeds 192 MiB; run a shorter readiness test.",
    "funding_run_limit": "Reduce the run budget to the limit in /public/funding-policy.",
    'source_not_publishable': 'The source did not pass the publication safety checks.',
    'screening_unavailable': 'Submission screening is temporarily unavailable.',
    'credential_scanner_unavailable': 'Credential screening is temporarily unavailable; retry with unchanged source and local evidence.',
    'builder_unavailable': 'The isolated builder is temporarily unavailable.',
    'source_package_too_large': 'Expanded harness source exceeds the review limit. Remove unused bundled files; retain runtime code and licenses. ZIP compression does not change the limit.',
    **{'submission_' + stage + '_rejected': 'Submission rejected during ' + stage + '.'
       for stage in ADMISSION_FIELDS},
}


ADMISSION_EXPECTATIONS = {**{code: ADMISSION_MESSAGES[code] for code in (
 'local_evidence_budget_cap_missing', 'local_evidence_budget_cap_invalid', 'local_evidence_budget_cap_insufficient')}, 'request_shape': 'The documented evaluation request envelope.',
 'source_package_too_large': 'Expanded source within the advertised byte limit; retain runtime code and licenses.',
 'protocol_mismatch': 'Match server_policy.protocol.',
 'evidence_mode_mismatch': 'Match server_policy.evidence_mode.',
 'problem_set_mismatch': 'Match server_policy.problem_set_digest.',
 'pricing_snapshot_unrecognized': 'The pinned schedule or a quote issued by this evaluator.',
 'pricing_quote_expired': 'An unexpired evaluator pricing quote.',
 'evaluation_schema': 'Schema v3, or v4 with an explicit models list; documented fields only.',
 'limit_fields': 'max_seconds and optional max_model_tokens.',
 'time_limit': 'A positive integer max_seconds.',
 'token_limit': 'null or a positive integer max_model_tokens.',
 'reasoning_effort': 'low, medium, high, xhigh or max.',
 'model_shape': 'A provider ID, exact model name and optional reasoning_effort.',
 'source_envelope': 'digest and archive_base64 fields.',
 'source_encoding': 'Valid base64 for the source bundle.',
 'source_digest_mismatch': 'The digest of the submitted harness snapshot.',
 'request_id_conflict': 'The unchanged original request for this request ID.',
 'codex_access_format': 'The supported temporary Codex access handoff.',
 'credit_limit': 'A positive max_model_credits value.',
 'model_unpriced': 'A pricing schedule covering the selected provider and model.',
 'authentication_required': 'A valid Yukon/evaluator login.',
 'source_not_publishable': 'Inspectable harness source without credentials, private files or '
                           'opaque archives.',
 'check_failed': None}

def safe_uuid(value):
    if not isinstance(value, str) or len(value) != 36:
        return None
    try:
        return value if str(uuid.UUID(value)) == value else None
    except ValueError:
        return None


class HTTPFailure(CatalystError):
    def __init__(self, status, details=None):
        self.status = status
        self.diagnostic_path = None
        self.diagnostic_write_failed = False
        self.saved_request_id = None
        self.before_evaluation = False
        self.details = {}
        if isinstance(details, dict):
            edge_id = details.get('edge_id')
            if isinstance(edge_id, str) and re.fullmatch(r'[a-f0-9]{32}', edge_id):
                self.details['edge_id'] = edge_id
            code = details.get('code')
            if isinstance(code, str) and code in ADMISSION_MESSAGES:
                self.details['code'] = code
            if code == 'source_not_publishable' and isinstance(details.get('source_findings'), list):
                rules = {'source-screening-size-limit', 'source-screening-complexity-limit',
                         'private-credential-or-service-file', 'nested-archive-not-reviewable',
                         'opaque-source-not-reviewable', 'embedded-credential', 'possible-credential'}
                findings = [{'file_index': item['file_index'], 'line': item['line'], 'rule': item['rule']}
                            for item in details['source_findings'][:10] if isinstance(item, dict)
                            and isinstance(item.get('rule'), str) and item['rule'] in rules
                            and type(item.get('file_index')) is int and 0 <= item['file_index'] < 10000
                            and type(item.get('line')) is int and 1 <= item['line'] <= 64 * 1024 * 1024]
                if findings:
                    self.details['source_findings'] = findings
            if code == 'local_evidence_not_private' and isinstance(details.get('evidence_findings'), list):
                rules = {'source-screening-size-limit', 'source-screening-complexity-limit',
                         'private-credential-or-service-file', 'nested-archive-not-reviewable',
                         'opaque-source-not-reviewable', 'embedded-credential'}
                findings = [{k: item[k] for k in ('event_index', 'rule', 'line')}
                    for item in details['evidence_findings'][:10] if isinstance(item, dict)
                    and type(item.get('event_index')) is int and 0 <= item['event_index'] < 6000
                    and isinstance(item.get('rule'), str) and item['rule'] in rules
                    and type(item.get('line')) is int and 1 <= item['line'] <= 64 * 1024 * 1024]
                if findings:
                    self.details['evidence_findings'] = findings
            stage, field = details.get('stage'), details.get('field')
            if isinstance(stage, str) and stage in ADMISSION_FIELDS:
                self.details['stage'] = stage
                if isinstance(field, str) and field in ADMISSION_FIELDS[stage]:
                    self.details['field'] = field
            reason = details.get('reason')
            if isinstance(reason, str) and reason in ADMISSION_EXPECTATIONS:
                self.details['reason'] = reason
                expected = ADMISSION_EXPECTATIONS[reason]
                if expected is not None:
                    self.details['expected'] = expected
            for name, pattern in (('expected_protocol', r'catalyst-evaluation-v[0-9]{1,3}'),
                                  ('expected_problem_set_digest', r'[a-f0-9]{64}')):
                value = details.get(name)
                if isinstance(value, str) and re.fullmatch(pattern, value):
                    self.details[name] = value
            mode = details.get('expected_evidence_mode')
            if isinstance(mode, str) and mode in {'remote', 'local-test', 'local-ecdsa'}:
                self.details['expected_evidence_mode'] = mode
            for name in ('correlation_id', 'request_id'):
                value = safe_uuid(details.get(name))
                if value is not None:
                    self.details[name] = value
            if status == 429 and isinstance(code, str) and code in QUOTA_MESSAGES:
                scope = details.get('scope')
                if isinstance(scope, str) and scope in {'account', 'global'}:
                    self.details['scope'] = scope
                for name in ('limit', 'current', 'requested', 'retry_after_seconds'):
                    value = details.get(name)
                    if type(value) is int and 0 <= value <= 2**53:
                        self.details[name] = value
            if status == 413 and code == 'source_package_too_large':
                for name in ('current', 'limit'):
                    value = details.get(name)
                    if type(value) is int and 0 <= value <= 2**40:
                        self.details[name] = value
            if isinstance(code, str) and code in ADMISSION_MESSAGES:
                value = details.get('retry_after_seconds')
                if type(value) is int and 0 <= value <= 2**53:
                    self.details['retry_after_seconds'] = value
        message = f"Evaluator returned HTTP {status}"
        code = self.details.get('code')
        if code:
            message += ': ' + ADMISSION_MESSAGES[code]
        if self.details:
            message += ' (' + ', '.join(f'{k}={v}' for k, v in self.details.items()) + ')'
        if 'source_findings' in self.details:
            message += '; file_index is zero-based in the saved source files sorted by relative path; line is one-based'
        super().__init__(message)

    def __str__(self):
        message = super().__str__()
        if self.before_evaluation:
            message += '; evidence upload failed before evaluation submission. Keep the harness and local run while diagnosing this error.'
        elif safe_uuid(self.saved_request_id):
            message += f'; saved request {self.saved_request_id} preserved.'
            message += (' Diagnose the rejection before retrying.' if self.status in (400, 413, 415, 422)
                        else ' Retry the same saved request ID; do not create a duplicate run.')
        if self.diagnostic_path is not None:
            message += f' Sanitized admission diagnostics: {self.diagnostic_path}'
        elif self.diagnostic_write_failed:
            message += ' Could not save admission diagnostics; retain the displayed IDs.'
        return message


def fetch(url: str, token: str, *, document=None, limit=4 * 1024 * 1024, timeout=30,
          model_token=None, output=None, expected_sha256=None, expected_size=None) -> bytes:
    if token or model_token is not None:
        credential_url(url, model_access=model_token is not None)
    private_headers = {}
    if model_token is not None:
        from catalyst.credentials import TOKEN_HEADER, validate_token
        validate_token(model_token)
        private_headers[TOKEN_HEADER] = model_token
    request = urllib.request.Request(
        url, data=canonical(document) if document is not None else None,
        headers={**({"Authorization": f"Bearer {token}"} if token else {}),
                 "Content-Type": "application/json", **private_headers},
        method="POST" if document is not None else "GET",
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            if output is None:
                content = response.read(limit + 1)
            else:
                import tempfile
                target = Path(output)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".artifact-", delete=False) as stream:
                        temporary = Path(stream.name)
                        hasher, size = hashlib.sha256(), 0
                        while chunk := response.read(1024 * 1024):
                            size += len(chunk)
                            if size > limit:
                                raise CatalystError("Artifact exceeds its declared download limit.")
                            hasher.update(chunk)
                            stream.write(chunk)
                    if size != expected_size or hasher.hexdigest() != expected_sha256:
                        raise CatalystError("Downloaded artifact does not match its verified checksum and size.")
                    temporary.replace(target)
                    temporary = None
                    return b""
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
    except urllib.error.HTTPError as error:
        # Only display bounded, typed admission fields and local message text.
        # Never echo arbitrary error text, provider diagnostics or credentials.
        status, details = error.code, None
        try:
            body = error.read(8193)
            if len(body) <= 8192:
                details = json.loads(body)
        except (ValueError, OSError, http.client.HTTPException):
            pass
        finally:
            correlation_id = safe_uuid(error.headers.get('X-Catalyst-Correlation-ID')) if error.headers else None
            edge_id = error.headers.get('X-Catalyst-Edge-ID') if error.headers else None
            error.close()
        if isinstance(edge_id, str) and re.fullmatch(r'[a-f0-9]{32}', edge_id):
            details = {**(details if isinstance(details, dict) else {}), 'edge_id': edge_id}
        if correlation_id:
            details = {**(details if isinstance(details, dict) else {}), 'correlation_id': correlation_id}
        raise HTTPFailure(status, details) from None
    except (urllib.error.URLError, http.client.HTTPException, OSError) as error:
        if isinstance(getattr(error, "reason", error), ssl.SSLCertVerificationError):
            raise CatalystError(
                "Evaluator TLS certificate verification failed; credentials were not sent. "
                "Check the evaluator URL, certificate and client trust store; do not disable TLS verification. "
                "The request remains resumable."
            ) from None
        raise CatalystError("Evaluator is unreachable; retry with unchanged inputs.") from None
    if len(content) > limit:
        raise CatalystError("Evaluator response exceeds the allowed size.")
    return content


def solver_fetch(base, route, bearer, *, document=None, limit=4 * 1024 * 1024, model_token=None,
                 output=None, expected_sha256=None, expected_size=None):
    if bearer or model_token is not None:
        credential_url(base + route, model_access=model_token is not None)
    private = {"model_token": model_token} if model_token is not None else {}
    if route == '/local-evidence':
        # A bounded 192 MiB upload includes server-side credential scanning.
        # It must not inherit a short polling/discovery request timeout.
        private['timeout'] = 180
    if output is not None:
        private.update(output=output, expected_sha256=expected_sha256, expected_size=expected_size)
    if not bearer.startswith("ykn_"):
        return fetch(base + route, bearer, document=document, limit=limit, **private)
    parts = urllib.parse.urlsplit(base)
    if (parts.username or parts.password or parts.query or parts.fragment or not parts.hostname
            or (parts.scheme != "https" and not (
                parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "::1"}))):
        raise CatalystError("Yukon login requires a trusted HTTPS evaluator endpoint.")
    cache_key = (base, hashlib.sha256(bearer.encode()).digest())
    for attempt in range(2):
        cached = _solver_sessions.get(cache_key)
        if cached is None or cached[1] <= time.monotonic():
            result = json.loads(fetch(base + "/auth/yukon", bearer,
                                      document={"protocol": "catalyst-yukon-session-v1"},
                                      limit=16 * 1024))
            if (not isinstance(result, dict) or result.get("protocol") != "catalyst-yukon-session-v1"
                    or not isinstance(result.get("access_token"), str)
                    or not re.fullmatch(r"cys_[A-Za-z0-9_.-]{1,4096}", result["access_token"])
                    or type(result.get("expires_in")) is not int
                    or not 60 <= result["expires_in"] <= 900):
                raise CatalystError("Evaluator returned an invalid login session.")
            evaluation_id(result.get("owner_id"))
            cached = (result["access_token"], time.monotonic() + result["expires_in"] - 30)
            if len(_solver_sessions) >= 8:
                _solver_sessions.clear()
            _solver_sessions[cache_key] = cached
        try:
            return fetch(base + route, cached[0], document=document, limit=limit, **private)
        except HTTPFailure as error:
            if error.status != 401 or attempt:
                raise
            # Authentication failed before dispatch (e.g. the server restarted).
            # Keep the same request body/operation key when renewing and retrying.
            _solver_sessions.pop(cache_key, None)


def endpoint() -> str:
    value = os.environ.get("CATALYST_EVALUATOR_URL", "https://3.21.93.126").rstrip("/")
    parts = urllib.parse.urlsplit(value)
    if (not parts.hostname or parts.username or parts.password or parts.query or parts.fragment
            or (parts.scheme != "https"
                and not (parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost", "::1"}))):
        raise CatalystError("Configure CATALYST_EVALUATOR_URL as a trusted HTTPS evaluator endpoint; "
                            "the current OpenRSI evaluator is https://3.21.93.126.")
    return value


def solver_token() -> str:
    bearer = (os.environ.get("YUKON_API_TOKEN") or os.environ.get("CATALYST_API_TOKEN")
              or os.environ.get("HILBERT_API_TOKEN") or os.environ.get("SUPABASE_ACCESS_TOKEN"))
    if not bearer:
        config_root = Path(os.environ.get("YUKON_CONFIG_DIR", str(Path.home() / ".config")))
        config_path = config_root / "yukon/config.json"
        if not config_path.exists() and not os.environ.get("YUKON_CONFIG_DIR"):
            config_path = config_root / "hilbert/config.json"
        config = read_json(config_path) if config_path.is_file() else {}
        bearer = config.get("token")
    if not isinstance(bearer, str) or not bearer or "\n" in bearer or "\r" in bearer:
        raise CatalystError("Log in with yukon login or set YUKON_API_TOKEN before requesting an evaluation.")
    return bearer
