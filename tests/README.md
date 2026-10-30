# Public tests

Run `make check` from the repository root. Tests cover public contracts, CLI,
source packaging, task resources and synthetic integration behavior. Private API
and worker tests belong in `openrsi-space-verifier`; live model calls are not CI tests.

`test_client_https.py` uses local TLS servers, disposable OpenSSL certificates and
synthetic secrets to check certificate rejection before HTTP, redirect refusal,
plaintext rejection and HTTPS credential renewal. Install the OpenSSL CLI to run
those socket tests; they never contact model providers or use real credentials.
