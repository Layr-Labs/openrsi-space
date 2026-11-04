# ECDSA problem and upstream compatibility

The authoritative OpenRSI assignment is the
[packaged problem statement](../src/openrsi_space/problem-set/ecdsa-fail/description.md).
Read the server-assigned statement during a run. Upstream documentation or a
newer upstream checkout does not replace that assignment.

The objective is secp256k1 point addition, minimizing average executed Toffoli
gates × peak qubits. The pinned verifier checks 9,024 shots, clean ancillas,
phase behavior and forward/reverse identity. See the assigned statement for the
complete interface and correctness requirements.

OpenRSI starts new research from a blank point-addition scaffold and neutral SDK,
with the shared paper library supplied at runtime. There is no valid starter
score. Editable candidate code belongs under the task's `candidate_paths`;
for the current scaffold, only UTF-8 `.rs` files belong in `src/point_add/`.
Keep research notes elsewhere. See the [harness contract](executable-harness.md).

## Documentation revision versus execution pin

The public release manifest pins execution to
[`62ae3d00d1e01d7bc640b5163cfea8dabffd8392`](https://github.com/Layr-Labs/ecdsafail-challenge/tree/62ae3d00d1e01d7bc640b5163cfea8dabffd8392).
The earlier upstream documentation comparison reviewed
[`4b2ec52fc55da796aa8f5ef851290297e8706424`](https://github.com/Layr-Labs/ecdsafail-challenge/tree/4b2ec52fc55da796aa8f5ef851290297e8706424)
on 2026-10-14. That review did not change the execution pin.

Use OpenRSI's assigned workspace and `evaluate` command, not a checkout of
upstream `main`, which may include other solvers' solutions or a different
interface. OpenRSI prohibits importing existing task solutions even where an
upstream challenge permits reuse. General-purpose harness reuse remains subject
to attribution and source-license requirements.

Run `openrsi-space problem current` before preparing a new evaluation. Compare
exact problem identities and starting conditions; retained runs keep their
original versions. See [compatibility](deployment-compatibility.md) and
[submission rules](cheat-filter.md).
