# Deterministic cheat screening

The initial filter is implemented in `src/catalyst/cheat_filter.py` and deployed
on Openclaw in release `20261008-history-screen-1`.
It supplements the pinned circuit verifier. It is not a proof that arbitrary
submitted code is safe or honest.

## Enforcement

- Before building a harness, screen its exact packaged source for embedded
  credentials, cloud metadata endpoints and host container-control sockets.
  Ordinary harness subprocess and model-gateway use remains allowed.
- Before each intermediate ECDSA evaluation, screen the extracted Rust module.
  A rejected module never reaches the scorer and receives `screen_rejected`.
  Dungeness records that status through its existing evaluator event mechanism.
- Before final verification, screen the frozen candidate bytes and bind the
  private report to their canonical digest.

Candidate screening rejects non-Rust/binary files, filesystem/process/network
access patterns, unsafe/FFI/assembly, external source inclusion and known
verifier paths. Comments discussing an unsafe design are ignored by code rules;
embedded credentials and sensitive endpoints are still screened in source text.
Reports contain rule, path and line only, never the matched source or secret.
Harness/final reports are retained in the owner's private traces.

The generated Dungeness execution checkout installs the same policy before
`serve.py` calls the unchanged pinned `grade.score_candidate`. The pure policy is
embedded in `serve.py`, which Dungeness already copies into the evaluator image.
These generated changes are included
in the execution checkout identity. The original Dungeness checkout and ECDSA
grading implementation are not edited. No candidate-capture hook is installed.

## Limits and review

This is conservative static screening. Obfuscation, dependency behavior,
algorithmic dishonesty and novel verifier exploits need additional review and
isolation; a passed scan is not security certification. False positives may
require changing code or operator review. There is no automatic bypass flag.
The no-network final verifier, restricted candidate paths, immutable receipts
and trusted model metering remain necessary.

Tests exercise direct and grouped imports, comment-separated paths, raw
identifiers, credential redaction, legitimate comments and the actual sidecar
screening hook. The previous live candidate was replayed through the filter
without a model call. Four adversarial candidates (filesystem access, grouped
process import, unsafe code and external source inclusion) were also rejected
before compilation in the actual pinned verifier container on Openclaw.
This is a bounded check of these attacks, not exhaustive adversarial testing.
