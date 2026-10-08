# Catalyst architecture

Develop and test locally on the Mac first. The initial remote MVP runs both the
authenticated API and the harness worker inside the existing VM reached through
`ssh openclaw`. The VM stays running and is reused across jobs. The worker builds
and runs harnesses in separate run workspaces/containers and verifies captured
candidates in a trusted workspace. No per-evaluation VM provisioning or teardown
is part of this MVP. Agent Compose, new cloud resources and a vault are
unnecessary. The current deployment uses Nginx for public HTTPS on port 443.

The initial challenge is exclusively **ecdsa.fail**, compared at **$20 and $200 checkpoints, plus Best achieved**. See [tier accounting](tier-accounting.md). Continuous
execution with budget checkpoints remains a proposal, not a scheduling decision.
The checkpoints do not cap a run's total spending; the solver chooses that
authorization independently.

```mermaid
flowchart TB
    subgraph LOCAL["Solver's computer"]
        DEV["Local agent and shared harness source"]
        CHECK["Pinned ECDSA verifier and reusable workspace"]
        CLI["Yukon / Catalyst CLI"]
        AUTH["Local renewable provider credentials"]
        DEV <--> CHECK
        DEV --> CLI
    end
    subgraph SERVER["Existing persistent VM: openclaw"]
        API["Authenticated API and job controller"]
        STORE[("Immutable source, build and evaluation records")]
        METER["Trusted temporary model access and credit metering"]
        API <--> STORE
        API --> METER
        subgraph WORKER["Worker on the same VM: per-run workspaces / containers"]
            BUILD["Untrusted source build"]
            RUN["Trusted Dungeness runner"]
            HARNESS["Submitted harness"]
            CAPTURE["Trusted candidate capture and checkpoint seals"]
            VERIFY["Isolated ECDSA verification"]
            BUILD --> RUN
            RUN --> HARNESS
            HARNESS --> CAPTURE
            CAPTURE --> VERIFY
        end
    end
    PROVIDER["Model provider"]
    YUKON["Yukon backend: receipt submissions and Pareto scores"]
    GITHUB["Challenge-owned GitHub workflow"]
    UI["Tier rankings and full performance-cost curves"]
    CLI -->|"Source, exact model, tier and limits"| API
    AUTH -->|"Temporary access via private authenticated channel"| METER
    API --> RUN
    HARNESS -->|"Scoped requests"| METER
    METER <--> PROVIDER
    METER -->|"Settled usage ledger"| CAPTURE
    VERIFY -->|"Metrics bound to immutable candidate digest"| STORE
    RUN -->|"Private traces and status"| STORE
    API -->|"Verification receipt"| CLI
    CLI -->|"Receipt only; no harness upload"| YUKON
    YUKON -->|"Create PR, dispatch pinned workflow"| GITHUB
    GITHUB -->|"Receipt, expected problem, GitHub OIDC"| API
    API -->|"Resolve submission owner via existing API"| YUKON
    API -->|"Stored verified judgment; no new run"| GITHUB
    GITHUB -->|"Trusted Pareto score artifact"| YUKON
    YUKON --> UI
```

## Identities and evidence

Source identity includes executable code, build recipe, dependencies,
instructions and knowledge. Runtime settings and the verification reference are
excluded from that source hash. Bind each evaluation separately to source,
server-built image digest, the ECDSA pin, exact provider/model, spending cap,
resource limits, pricing digest, policy digest and authenticated owner.

Use distinct request, build and evaluation IDs. Retries reuse their original
operation key; deliberate repeats get a new evaluation ID. The server can reuse
an immutable build for unchanged source. Changed source or settings require new
remote evidence. A reference file or local score is not an attestation.
Yukon receives only the receipt. Its standard GitHub Actions runner dispatches
the challenge workflow, which resolves it with Catalyst. The submitted
receipt identifies the previously evaluated harness, even if local files have
subsequently changed. Catalyst retains that harness and its evaluation settings;
Yukon does not need another source upload or a local source comparison.

Official measurements require trusted usage settlement, immutable candidate
capture, checkpoint seals and independent verification. Keep the complete
verified curve, infrastructure usage, and private traces before cleaning up the
job's processes, containers and temporary workspace. Keep the remote VM running
for subsequent jobs.
Public metrics contain allowlisted result fields; provider credentials and raw
traces stay out of submissions and public artifacts.

## Credentials and implementation boundary

The final service will receive temporary provider access over authenticated HTTPS
(port 443), held only in memory by a trusted component for the active run.
User-provided provider credentials must never be persisted, even encrypted.
The durable queue stores non-secret grant references; builds receive no model
access, and submitted harnesses use a scoped gateway rather than raw provider
credentials. Discard temporary access on completion, failure, cancellation or
expiry. A service restart requires fresh user authorization.

Renewable credentials and refresh operations stay on the user's machine.
Preserve those original credentials during cancellation and cleanup.
The credential endpoint, memory-only lifecycle and protections against disk
copies still need implementation; this MVP keeps model access disabled.
See [runtime requirements](runtime-platform-requirements.md).

Implemented: local packaging/build/smoke tools, Dungeness adapter, pinned ECDSA
workspace, tier viewer, credit/checkpoint validators, remote client and submission
workflow. The local API now persists jobs, ownership, immutable submission
bindings and results in SQLite. The server starts and supervises a separate
worker process, which runs the real Dungeness/Docker path, retains private
evidence and independently verifies a frozen candidate. The pinned ECDSA
baseline runs with model access disabled; a smaller circuit fixture uses a mock
provider to test accounting. Worker failure stops the API; service shutdown stops
the owned worker and its reported execution processes. Queued work survives,
and interrupted attempts are marked failed without automatic replay.
The VM deployment runs under `screen`, validates solver keys against Yukon dev
and exchanges them for memory-only sessions. No separate Catalyst solver
password is required. The current integration uses stock Yukon's GitHub Actions runner,
receipt-only archives and a signed-OIDC result endpoint. Experimental custom
Yukon patches are preserved but not required. See [the end-to-end guide](github-actions-e2e.md) and
[the reproducible local check](local-evaluation.md).

Current priority: publish the HTTPS workflow, authorize GitHub OIDC, register
the benchmark in Yukon dev and validate one hosted submission. The dev GitHub
App is installed; the account still needs benchmark-import permission.
Temporary provider access, runtime checkpoint capture and credit reservations
remain implementation work. User cancellation is deferred. Real research runs
and adversarial testing follow the pipeline test. Remote viewer integration and
artifact retention/cleanup policy are later operational work.
Local fixture modes remain separate and cannot be relabeled as remote ECDSA evidence.

## Service extraction

The reusable verification service owns upload, queueing, execution, authentication,
immutable receipts and result retrieval. Catalyst owns ECDSA task pins, verification
and scoring policy, model-credit rules and the challenge workflow. Keep those
boundaries explicit while validating this integration; a separate service package
or repository can follow without changing the solver's receipt workflow.
