# ECDSA upstream statement review

**2026-10-15 scaffold revision:** the new default reconstructs from a blank
point-addition stub and the pinned Dungeness neutral SDK. It retains the
upstream interface/metric and full 9,024-shot acceptance requirement, with
progressive failure checks. This changes the problem manifest and starting
conditions; the earlier documentation-only compatibility notes below describe
the previous revision, not this rollout.

Reviewed on 2026-10-14 against upstream `main` at
[`4b2ec52fc55da796aa8f5ef851290297e8706424`](https://github.com/Layr-Labs/ecdsafail-challenge/tree/4b2ec52fc55da796aa8f5ef851290297e8706424).
“Latest” here means this exact reviewed commit, not a moving branch dependency.

The authoritative statement is now maintained in Catalyst at
[`src/catalyst/problem-set/ecdsa-fail/description.md`](../src/catalyst/problem-set/ecdsa-fail/description.md).
Service initialization copies that statement into its versioned problem package.
Dungeness's older task statements remain available for historical standalone
runs, but do not define newly initialized Catalyst problem packages.

| Area | Finding |
| --- | --- |
| Objective and interface | Unchanged: secp256k1 point addition, four 256-element registers, average executed Toffoli × peak qubits, minimized. |
| Correctness | Unchanged: 9,024 shots, clean ancillas, phase checks, forward/reverse identity. |
| Editable source | Still `src/point_add/`; current README also recommends Markdown memory notes there. |
| Reference numbers | Upstream labels 3,942,753 Toffoli / 2,715 qubits as the **initial** circuit, not the current main result. |
| Extra hint | Dungeness's claimed known-achievable score of 1,480,849,785 is absent from upstream and is not included in the Catalyst statement. |
| Participation | Upstream documents its own ECDSA CLI. A Dungeness research task uses the supplied evaluator; Catalyst's solver documentation describes remote evaluation and Yukon receipt submission. |
| Shared solutions | Upstream welcomes reusing contributors' leads. Catalyst evaluates autonomous research and prohibits importing existing submitted solutions; Catalyst's policy continues to apply. |
| Executable changes | Current upstream sandboxes the untrusted circuit builder, adds zstd-compressed `QECCOPSZ` operation files and the zstd dependency, and updates setup/GitHub Actions support. |
| Lean | No Lean source or Lean verification step appears in the reviewed main tree. |

The README still mentions `src/main.rs` and `cargo run --release -- --note`,
although the repository uses `src/bin/build_circuit.rs` and
`src/bin/eval_circuit.rs`. Catalyst points users to its commands, which call the
pinned `setup.sh` and `benchmark.sh`, rather than copying that stale invocation.

## Documentation revision versus execution pin

The execution pin remains
[`62ae3d00d1e01d7bc640b5163cfea8dabffd8392`](https://github.com/Layr-Labs/ecdsafail-challenge/tree/62ae3d00d1e01d7bc640b5163cfea8dabffd8392)
in `ecdsa-fail/releases/unversioned.json`. Core mathematical requirements are the same.
The newer documentation does not claim that the current sandboxing or compressed
operation format has been deployed in Catalyst.

Do not silently repin the starting workspace to current upstream main: it
contains accumulated solver solutions. Adopting newer trusted verifier code
requires a separately reviewed contract update that preserves the intended
baseline, updates the circuit-format adapter and dependencies, tests valid and
invalid candidates, and records a new problem version. Old receipts keep their
original problem identity.

The public manifest is deliberately unchanged by this documentation update, so
existing receipt bindings remain valid. New service initialization packages
the Catalyst statement; that content
participates in the problem package's snapshot hash. Existing service installations
retain their stored statement until an explicit operator migration; this source
change alone does not update a running server.

A future challenge may have its own public repository and reuse Dungeness's
generic problem-service wiring, but the runtime does not require one repository
per problem.
