# Catalyst architecture

Develop and test locally on the Mac first. The initial remote MVP runs both the
authenticated API and the harness worker inside the existing VM reached through
`ssh openclaw`. The VM stays running and is reused across jobs. The worker builds
and runs harnesses in separate run workspaces/containers and verifies captured
candidates in a trusted workspace. No per-evaluation VM provisioning or teardown
is part of this MVP. Agent Compose, new cloud resources, a vault and a reverse
proxy are unnecessary for the initial implementation.

The initial challenge is exclusively **ecdsa.fail**, compared at **$20 and $200 checkpoints, plus Best achieved**. See [tier accounting](tier-accounting.md). Continuous
execution with budget checkpoints remains a proposal, not a scheduling decision.

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
    YUKON["Yukon identity and submissions"]
    GH["GitHub Actions: resolve existing evaluation"]
    UI["Tier rankings and full performance-cost curves"]
    CLI -->|"Source, exact model, tier and limits"| API
    AUTH -->|"Temporary access via private authenticated channel"| METER
    API --> RUN
    HARNESS -->|"Scoped requests"| METER
    METER <--> PROVIDER
    METER -->|"Settled usage ledger"| CAPTURE
    VERIFY -->|"Metrics bound to immutable candidate digest"| STORE
    RUN -->|"Private traces and status"| STORE
    CLI <--> YUKON
    YUKON --> GH
    GH <-->|"Authorize source/settings/result reuse; no new paid run"| API
    GH -->|"Public judgment"| YUKON
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

Official measurements require trusted usage settlement, immutable candidate
capture, checkpoint seals and independent verification. Keep the complete
verified curve, infrastructure usage, and private traces before cleaning up the
job's processes, containers and temporary workspace. Keep the remote VM running
for subsequent jobs.
Public metrics contain allowlisted result fields; provider credentials and raw
traces stay out of submissions and public artifacts.

## Credentials and implementation boundary

Renewable credentials remain on the solver's machine. A private authenticated
channel supplies temporary provider access to trusted execution components.
The submitted harness receives scoped model access; builds receive none.
The implementation must preserve original credentials during cancellation and
cleanup. No vault or reverse proxy is required. API and subscription renewal
flows still need implementation; see [runtime requirements](runtime-platform-requirements.md).

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
The private VM deployment runs under `screen` with provisioned solver and Yukon
consumer keys. The new Yukon backend provider retrieves stored judgments
directly and validates them as Pareto results. See [VM setup](remote-vm.md) and
[the reproducible local check](local-evaluation.md).

Pending: the hosted Yukon provider release, automatic account/grant provisioning, temporary
provider access and renewal for ECDSA research runs, runtime checkpoint
capture and credit reservations, artifact retention policy, hosted benchmark
registration and the real Yukon board integration. Local fixture modes remain
separate and cannot be relabeled as remote ECDSA evidence.
