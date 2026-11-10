# OpenRSI architecture

OpenRSI evaluates autonomous research harnesses on assigned problems. Local tests
use the solver's model access; Eigen Labs funds fresh remote verification.

```text
harness + local records → admission → isolated remote run → independent verification
                                                               ↓
                                                     automatic dashboard result
                                                               ↓ optional
                                                     Yukon repository record
```

## Components and boundaries

| Component | Responsibility |
| --- | --- |
| Solver's coding agent | Builds and tests the harness; reports readiness and diagnoses failures. |
| Submitted harness | Runs autonomously from the supplied scaffold using assigned resources and gateway routes. |
| OpenRSI CLI | Packages source/evidence, manages the tested local runtime, submits and monitors runs. |
| Dungeness | Runs the harness, meters model access and records candidate evaluations and usage. |
| Verifier | Screens submissions, manages isolated runs, independently verifies results and issues receipts. |
| Yukon | Provides account identity, hosts the UI and optionally records a published receipt. |

The [state model](submission-states.md) defines progress and separate outcomes.
Verification, source availability and optional Yukon publication can fail
independently. A receipt retrieves a retained result; publishing it never repeats
research. A source digest identifies bytes, not safe code or an authenticated
historical local bill.

The harness receives a scoped gateway route and placeholder authentication, not
the platform model key. Local credentials stay outside source and evidence.
Private evidence is screened and reviewed by a third-party LLM. Public source,
owner diagnostic logs and operator evidence have separate visibility; see
[artifacts and publication](artifact-sharing.md).

## Repositories

| Repository | Contents |
| --- | --- |
| `openrsi-space` | Solver CLI, contracts, challenge resources and documentation. |
| `dungeness` | Local and hosted execution runtime. |
| `openrsi-space-verifier` | Private hosted service and operator tools. |
| `yukon` | Identity, receipt publication and UI. |

Use the current standalone client while keeping any Yukon receipt-checking
checkout pinned. Updating the client does not deploy the hosted service.
See [runtime compatibility](client-runtime-versions.md), [code ownership](maintainers/development.md#ownership)
and [remote API](maintainers/remote-api.md).

## ECDSA assignment and upstream provenance

The [packaged statement](../src/openrsi_space/problem-set/ecdsa-fail/description.md)
and server-assigned task are authoritative. New research starts from a blank
point-addition scaffold and neutral SDK, with the library supplied at runtime.
There is no valid starter score. The verifier checks 9,024 shots, clean ancillas,
phase behavior and forward/reverse identity. The objective is average executed
Toffoli gates × peak qubits; lower is better.

The release manifest pins execution to
[`62ae3d00d1e01d7bc640b5163cfea8dabffd8392`](https://github.com/Layr-Labs/ecdsafail-challenge/tree/62ae3d00d1e01d7bc640b5163cfea8dabffd8392).
The earlier documentation comparison used
[`4b2ec52fc55da796aa8f5ef851290297e8706424`](https://github.com/Layr-Labs/ecdsafail-challenge/tree/4b2ec52fc55da796aa8f5ef851290297e8706424)
on 2026-10-14; it did not change execution. Use the assigned workspace and
`evaluate`, not upstream `main`, which may contain other solutions or a different
interface. Follow [candidate and source rules](source-and-build-rules.md), even where
upstream permits broader reuse. `problem current` discovers the active release;
retained runs preserve their original identities.
