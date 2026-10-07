> Background vision. The initial challenge is now ECDSA-only at $20 and $200 checkpoints
> plus Best achieved. See [the current contract](tier-accounting.md)
> and [architecture](architecture.md); broader problem authoring remains future work.

Original draft: Researcher agency (draft)

Our goal is to maximize academic researchers’ agency: their ability to choose meaningful questions, explore possible approaches, and use evidence to decide what to pursue next.

Yukon already supports part of this process through curated problems, open solver participation, and rigorous verification. One bottleneck is sourcing scientifically meaningful problems with reliable verifiers. A natural next step is to help researchers develop and refine these problems through the work of solving them.

!Screenshot 2026-09-28 at 4.52.49 PM.png

Research often involves a two way search. Sometimes we have a problem and look for the tools to solve it. Other times, we discover a tool or insight and recognize a problem it could unlock. An idea encountered months earlier could suddenly become useful when a new problem gave it context.

Suppose problems and tools as two sets of moving balls. Progress happens when a problem meets an approach that can address it. Intuition guides their movement, drawing on accumulated knowledge and experience.

Researchers build that intuition through reading, experimentation, and discussion. But our attention is limited, switching directions takes effort, and familiar methods shape what we notice. AI can help us explore more connections and test them faster—like raising the temperature in the room. Researchers still provide direction and judge which connections matter.

Yukon currently holds the problem relatively fixed while agents search for solutions. The opportunity is to help researchers move both sides: explore new approaches while revising the question, assumptions, or desired properties in response to evidence.

!Screenshot 2026-09-28 at 4.53.28 PM.png

This suggests a research workflow with a continuous feedback loop:

1. **Start with a scientific challenge.** A researcher identifies something worth understanding or improving. The exact problem may still be uncertain.
2. **Frame a testable question.** Specify the claim, assumptions, constraints, and evaluation criteria. A mathematical claim needs a valid proof or counterexample, with formal checking where feasible. A systems claim needs reproducible experiments, meaningful baselines, and controlled measurements.
3. **Run and record attempts.** Researchers and AI agents explore approaches within explicit budgets. Preserve the methods, results, failures, and resource costs so later work can build on them.
4. **Review the evidence and choose the next step.** An attempt may produce a positive result, a supported negative result, or remain inconclusive. A failed search is not a proof of impossibility. Researchers use the evidence to continue, change methods, revise the problem, or stop.
5. **Produce and reuse the research outputs.** Validated findings can become papers, proofs, software, datasets, or experimental tools. Both successful and unsuccessful attempts can inform future questions.

Feedback should follow successful attempts as well as failures. A solution may expose a more interesting question; a counterexample may reveal which assumption needs to change. A verifier establishes whether a result meets the stated criteria. Researchers must also judge whether those criteria capture a worthwhile scientific question.

Yukon already has important foundations: problem setting, solver infrastructure, verification, and research outputs. The proposed addition is a structured loop connecting solver evidence back to researcher-directed problem formulation.

The first development priorities are:

- **Useful feedback.** Identify which information helps researchers revise a problem: counterexamples, partial progress, failed approaches, performance bottlenecks, or sensitivity to assumptions. Make previous attempts available as a reusable knowledge base.
- **Reproducible, budgeted experiments.** Provide consistent test environments, explicit evaluation criteria, and accounting for tokens, compute, and time.
- **Traceable problem evolution.** Record how each new formulation relates to the previous one: what changed, what evidence motivated the change, and why it opens a scientifically valuable opportunity.

We should evaluate this workflow by whether it helps researchers make better decisions and pursue meaningful questions with greater independence. Useful measures include time to a well-supported decision, reuse of prior work, and the quality of the resulting research.
