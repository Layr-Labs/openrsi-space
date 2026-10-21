# EvoX-inspired Codex research harness

General-purpose adaptation of [EvoX, sections 3–4](https://arxiv.org/abs/2602.23413),
using pinned Codex CLI 0.153.3 as both solution generator and strategy generator.
This is an independent implementation, not a reproduction of the authors' full
SkyDiscover framework or its reported results.

The controller executes bounded solution turns, keeps evaluated candidates,
selects parents and inspirations, and revises a validated JSON search policy
after three turns without a meaningful improvement. Meta-turns see population
statistics and earlier strategy outcomes. Invalid strategy proposals fall back
to the previous policy. All inference, including meta-turns, uses the same
assigned model and metered gateway.

Compared with the paper, this small-budget adaptation uses declarative policies
instead of generated Python strategies and normalized relative progress instead
of its particular strategy reward formula. Candidate generation is an actual
Codex coding session, with shell tools and access to assigned resources.

No task-specific papers, solution code, heuristics or previous run outputs are
included. The runtime task supplies those resources. Snapshots and research
memory are generated during the run. Final output restores the best locally
checked candidate; independent service verification determines the real score.

The included evaluation requests GPT-6 Astra/high, 20 benchmark model credits,
no model-token ceiling and 2,700 seconds. Credits are reference-price accounting,
not a promise of an exact cash charge. The controller stops starting turns near
the cap and reserves time for candidate retention. Gateway accounting remains
authoritative; an in-flight response can cross a cap.
