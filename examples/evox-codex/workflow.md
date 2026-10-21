# Adaptive research workflow

Follow the assigned task, allowed edit paths and evaluation contract. This is a
general research controller, not a source of task-specific answers. All model
requests must use the assigned gateway. Do not inspect credentials, contact
public model endpoints or change the evaluation machinery.

Read the assigned description and knowledge-base catalog before selecting an
approach. Fetch relevant resources through the listed internal URLs, respecting
their media types. Use pdftotext for PDFs. Record useful references and findings
in RESEARCH.md outside the candidate directory; do not bulk-download the library.
The starting workspace may be a blank scaffold. Establish a correct candidate
before optimizing; never assume an existing valid solution.

The controller maintains a population of evaluator-checked snapshots and a
history of search strategies. A solution turn proposes one focused experiment
using the selected parent, variation operator and inspiration candidates. Learn
from failed experiments and evaluate concrete changes, rather than repeatedly
planning. A strategy turn revises the search policy when a window stagnates.
Strategy changes preserve the population.

Before the first evaluation, determine whether the task minimizes or maximizes
its numeric score. Evaluate every candidate worth retaining with:

    python3 /opt/harness/population.py check --direction minimize --note "hypothesis and change"

Use maximize instead when required by the task. This helper evaluates a frozen
snapshot via evaluate --json; it never accepts a claimed score. Successful
snapshots are retained, including diverse non-best candidates. Invalid attempts
are logged and cannot replace the best candidate. The supervisor also checks
the candidate when each solution turn ends and restores the best at final exit.

Read the helper's full feedback. If a long experiment produces an intermediate
valid result, checkpoint it immediately. Keep the best result safe. Leave
RESEARCH.md concise: current implementation, evidence, unsuccessful ideas,
relevant resource paths, and a concrete next experiment. Local observations are
research feedback; the platform independently verifies final results.

Use run-status when available to inspect actual consumption and remaining time.
Respect the deadline given for this turn. Budget or time exhaustion means stop
requesting inference and retain checked output. Do not invent usage or scores.
