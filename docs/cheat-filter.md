# Autonomous research and anti-cheat policy

Catalyst evaluates autonomous research harnesses. A harness must develop its
candidate during its metered run. It must not replay, embed, retrieve or reproduce
an existing ECDSA GitHub or leaderboard solution, including a memorized solution
encoded in prompts, code or knowledge files. Disguising copied code is also prohibited.

**Submit a general-purpose harness, without problem-specific material.** This
includes ECDSA-specific papers or links, notes, dossiers, circuit strategies,
optimization hints, precomputed answer tables, candidate code and historical
baseline implementations—even when the solver wrote them. Build steps and
dependencies must not import that material either.

General-purpose agents, research loops, compilers, framework dependencies and
retrieval tools are allowed. Incidental problem names, submission metadata and
interface paths are allowed when they convey no solution knowledge.

The trusted task service supplies the problem statement, blank scaffold, neutral
SDK and the same pinned **50-paper library** to every run. The agent may read those
papers, index them, develop strategies and generate candidates during its metered
run. Those trusted resources and newly generated candidates are outside the
submitted-material prohibition. See [the library endpoint](problem-service.md#shared-paper-library).

The remote verification service checks submitted material and resulting candidates.
It consults the challenge's published solutions when screening for copied answers.
Screening can reject a run before model execution or reject a produced candidate.
A run rejected after model calls can still consume the solver's model allowance.
Failures return a reason; a rejected run cannot issue a valid score receipt.
The admission reviewer checks every submitted text file. Opaque files that cannot
be reviewed, unavailable screening, and uncertain findings block admission rather
than receive a pass. Such failures are not an accusation of cheating. A private
`source-audit.json` report identifies the category and source location when the
reviewer finds a violation. Keep submitted material inspectable.

Use `catalyst remote status EVALUATION_ID` and `catalyst remote wait EVALUATION_ID`
to inspect the outcome. Keep the evaluation ID and rejection reason when reporting
an apparent false positive. Do not modify a harness simply to evade detection.

Screening is not a proof that all cheating will be detected. Independent circuit
verification remains required for every scored result. Screening implementation,
corpus operations and reviewer configuration live in the private `catalyst-verifier`
repository; the public policy applies regardless of implementation details.
