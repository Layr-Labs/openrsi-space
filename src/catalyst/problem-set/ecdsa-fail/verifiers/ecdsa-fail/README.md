# ECDSA Fail Verifiers

ECDSA Fail uses two verifier bundles because the public challenge changed its
candidate and evaluation interface during its Git history. They are historical
compatibility layers, not two interchangeable ways to grade the same source
tree.

| Bundle | Checkpoint interface | Candidate path | Use |
|---|---|---|---|
| `experiment-bin/` | `point-add-file-v1` | `src/point_add.rs` | Earliest sampled challenge state |
| `benchmark-sh/` | `point-add-module-v1` | `src/point_add/` | Later sampled challenge states |

The earliest checkpoint predates the later `benchmark.sh` workflow. Its
candidate is a single Rust file and must be compiled with the evaluator pinned
to that historical commit. Later checkpoints expose a module directory and use
the upstream split build/evaluate benchmark from the selected checkpoint.

Each checkpoint declares the interface present at that commit. The
`ecdsa-fail` task maps that interface to the compatible verifier bundle:

```text
checkpoint -> interface -> candidate paths + verifier
```

Keeping both bundles allows Dungeness to replay each public checkpoint against
its contemporaneous contract without rewriting old source states to fit the
newer interface.

The module-interface bundle applies a commit-pinned streaming-I/O backport to
the challenge-start and interpolated checkpoints. Those revisions otherwise
hold both `Vec<Op>` and a second complete serialized byte buffer while writing
or reading `ops.bin`. The backport preserves the framing and scoring contract,
but removes the duplicate allocation. The frontier checkpoint already contains
streaming and compression upstream. The older single-file interface is
unchanged and keeps its larger verifier memory envelope.
