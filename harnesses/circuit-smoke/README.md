# Circuit smoke-test harness

This is an editable, submission-ready harness for the current local test service.
It makes one model request through Dungeness's gateway, checks the returned circuit
on all eight possible inputs, and writes `candidate.json`. The service then
independently verifies that file in a separate container.

The local service supplies a mock model response. Expected verified performance
is `1 Toffoli × 3 qubits = 3` at `0.25` synthetic model credits, with no provider
charge. This is a pipeline test, not an ECDSA solver.

With the local service running and the client environment configured as in
[`docs/local-evaluation.md`](../../docs/local-evaluation.md), submit from the
Catalyst repository root:

```sh
.venv/bin/catalyst --state .catalyst/local-manual/client remote submit \
  harnesses/circuit-smoke --wait
```

The submission contains `agent.py`, its Dockerfile, manifest and instructions.
`evaluation.json` carries the local test grant reference and spending limits
separately; it contains no token. On completion the client writes
`verification.json` here and retains private results and traces in client state.

The worker builds the uploaded source and passes that exact build to the trusted
Dungeness/Harbor adapter. The adapter executes the manifest's entrypoint,
`python3 /opt/harness/agent.py`. Dungeness supplies execution and accounting;
the submitted `agent.py` is the solver.

Change `agent.py` or the instructions to experiment. A new submission after
completion creates another evaluation. The captured candidate contains
`"harness": "circuit-smoke"` so its origin is easy to recognize in private traces.
