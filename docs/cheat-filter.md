# Autonomous research and anti-cheat policy

OpenRSI evaluates autonomous research harnesses. A harness must develop its
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
SDK and the same pinned **eight-paper library** to every run. The agent may read those
papers, index them, develop strategies and generate candidates during its metered
run. Those trusted resources and newly generated candidates are outside the
submitted-material prohibition. See [the library endpoint](problem-service.md#shared-paper-library).

Submissions and produced candidates are checked against these rules. A rejection
can occur before execution or after model usage; charges already incurred still
count. A rejected candidate cannot establish a valid score.

Keep submitted material inspectable. A review failure or inconclusive result is
not an accusation of cheating. Read the returned reason and any reported source
location, and retain the request or evaluation ID when asking for help.

Use `openrsi-space remote status EVALUATION_ID` and `openrsi-space remote wait EVALUATION_ID`
to inspect the outcome. Keep the evaluation ID and rejection reason when reporting
an apparent false positive. Do not modify a harness simply to evade detection.

Screening is not a proof that all cheating will be detected. Independent circuit
verification remains required for every scored result. The published rules apply
to every submission.
