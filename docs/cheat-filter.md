# Autonomous research and anti-cheat policy

Catalyst evaluates autonomous research harnesses. A harness must develop its
candidate during its metered run. It must not replay, embed, retrieve or reproduce
an existing ECDSA GitHub or leaderboard solution, including a memorized solution
encoded in prompts, code or knowledge files. Disguising copied code is also prohibited.

Research papers, ordinary dependencies, legitimate tools and the pinned starting
baseline are allowed. Attribute external knowledge and dependencies in your
submission note. A paper used as background is not permission to import someone
else's completed benchmark submission.

The remote verification service checks submitted material and resulting candidates.
It consults the challenge's published solutions when screening for copied answers.
Screening can reject a run before model execution or reject a produced candidate.
A run rejected after model calls can still consume the solver's model allowance.
Failures return a reason; a rejected run cannot issue a valid score receipt.

Use `catalyst remote status EVALUATION_ID` and `catalyst remote wait EVALUATION_ID`
to inspect the outcome. Keep the evaluation ID and rejection reason when reporting
an apparent false positive. Do not modify a harness simply to evade detection.

Screening is not a proof that all cheating will be detected. Independent circuit
verification remains required for every scored result. Screening implementation,
corpus operations and reviewer configuration live in the private `catalyst-verifier`
repository; the public policy applies regardless of implementation details.
