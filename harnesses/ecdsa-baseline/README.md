# Real ECDSA baseline harness

This harness retains the actual ecdsa.fail starting `src/point_add` module at
commit `62ae3d00d1e01d7bc640b5163cfea8dabffd8392`. It runs through
Dungeness/Harbor and makes no model requests. The worker captures the Rust module
and independently compiles and verifies it with the pinned ECDSA verifier.
This establishes the starting score; it does not claim a circuit improvement.

Use the real ECDSA service, not the tiny circuit fixture service.
From the Catalyst repository root, initialize it once:

```sh
.venv/bin/catalyst local-ecdsa-init .catalyst/local-ecdsa \
  --dungeness /Users/bxue/Documents/dungeness-main
```

Start the service in one terminal; it manages the worker:

```sh
.venv/bin/catalyst --state .catalyst/local-ecdsa/service evaluator-serve \
  --local-auth --auth-file .catalyst/local-ecdsa/auth.json \
  --problem-set .catalyst/local-ecdsa/problem-set.json --port 8778
```

In another terminal, configure the client and submit:

```sh
export CATALYST_EVALUATOR_URL=http://127.0.0.1:8778
unset CATALYST_LOCAL_TEST CATALYST_LOCAL_PROBLEM_SET
export CATALYST_LOCAL_ECDSA=1
export CATALYST_API_TOKEN="$(.venv/bin/python -c \
  'import json; print(json.load(open(".catalyst/local-ecdsa/client-tokens.json"))["solver"])')"

.venv/bin/catalyst --state .catalyst/local-ecdsa/client remote submit \
  harnesses/ecdsa-baseline --wait
```

The service uses local authentication and labels evidence `local-ecdsa`. The
problem, candidate and verifier are real. There are no canned model responses:
the model endpoint rejects requests and has no real provider credentials.
The model name and positive credit ceiling in `evaluation.json` preserve the
client contract; actual model usage for this baseline is zero.

The verifier performs the real Rust build and circuit simulations, so this run
needs considerably more memory and time than the circuit smoke test. The pinned
Dungeness verifier includes its recorded low-memory streaming backport; it uses
the challenge's own benchmark and scoring formula. Verification artifacts and
traces remain private in the client and service state directories.
