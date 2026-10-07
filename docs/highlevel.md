> Background vision. The initial challenge is now ECDSA-only at $20 and $200 checkpoints
> plus Best achieved. See [the current contract](tier-accounting.md)
> and [architecture](architecture.md); broader problem authoring remains future work.

Reports from academic groups on facing AI https://simons.berkeley.edu/AITCSreport?inline=, https://cmsa.fas.harvard.edu/media/2026/09/Summit-on-PhD-Math-Education-in-the-Age-of-AI.pdf

### **Research Harness Platform**

We want to help PhD students and academic researchers find AI harnesses that work well for their research problems, compare their performance and cost, and contribute improvements.

The platform is organized around a matrix:

- **Rows:** research problems.
- **Columns:** research harnesses.
- **Entries:** observed performance and cost under a specified model and execution configuration on the problem

A harness is the reusable setup around a model: its instructions, tools, domain knowledge, and strategy for working on a problem.

The underlying idea is that research depends on matching problems with suitable knowledge and methods. Different harnesses may be useful for different kinds of problems. The platform makes those differences visible and allows the community to improve them.

research-harness.html

### **How researchers use it**

Researchers can participate in three ways:

1. **Find a harness.** Select problems related to their work, compare the available results, and adopt a promising harness.
2. **Improve a harness.** Use their domain knowledge to develop a better approach and share it with acknowledgment.
3. **Contribute a problem.** Publish a research problem so others can attempt it and evaluate their harnesses against it.

Problems may come from cryptography, theoretical computer science, mathematics, and other fields. Researchers can contribute entirely new problems or variants of existing ones—for example, by weakening an assumption or changing the desired result.

A new problem creates another opportunity to evaluate existing harnesses. A new harness can be tested on relevant existing problems.

### **What the matrix tells us**

The matrix should help researchers answer: “Which harness is worth trying for my problem, given my budget?”

It can be sparse. A harness designed for one field does not need to perform well in every field, and an empty entry means the combination has not been evaluated.

Performance must be defined for each problem. Depending on the task, it might mean finding a valid solution, improving an objective, or achieving a specified partial result. Comparisons should show the model and budget used, because these also affect the outcome.

A harness should be reusable across related problems. Its value comes from a method that transfers, even if it is specialized to a particular domain.

### **Can we trust the results?**

The central concern is whether a harness demonstrates reusable problem-solving ability or succeeds through task-specific answers and overfitting.

An initial evaluation setting can restrict internet access while permitting model calls and approved resources. This makes the conditions easier to control, although it may also reduce the harness’s usefulness. An internet-enabled setting could be supported separately.

Restricting internet access does not eliminate overfitting, as harness or knowledge base can overfitting a particular problem. We can alleviate by

- Testing an unchanged harness on problems introduced after its submission.
- Repeating reported runs and inspecting their outputs.
- Allowing researchers to report suspicious results or failed reproductions.
- Using cheaper models to screen submissions and prioritize further review.

Performance on later problems is evidence of generalization, rather than a guarantee. Results should clearly state whether they are self-reported or independently checked.

### **How do we afford evaluation?**

Evaluating every harness on every problem is expensive. With M problems, N harnesses, and an average cost of K per run, one complete pass costs approximately M × N × K. Repeated runs increase that cost.

We do not need to populate the entire matrix immediately. Contributors can report results on problems relevant to their harness, with supporting outputs and execution details. The platform can prioritize verification of results that appear useful to researchers.

Possible execution options include contributor-funded local runs, paid platform runs, and runs using researchers’ own API accounts through supported authentication methods.

The interface should make the strength of the evidence visible, so that self-reported results can be useful without being mistaken for verified results.

### **What can be reused**

Existing problems help evaluate new harnesses. New problems help test whether older harnesses generalize. Harness authors can reuse and improve one another’s components, with attribution.

The platform can also share execution tools, model adapters, budget accounting, result records, and some verifiers. Problem formulation and evaluation criteria will often require domain-specific work.

### **The assumption we are testing**

We expect harness design to affect performance beyond model choice alone. The platform should make that effect measurable.

If particular harnesses provide little improvement under comparable conditions, that is also useful information for researchers deciding where to invest their effort.

### Architecture

A cli that can

- add local problems
- choose agent to work on problems, and obtain scores and results
- publish problems into the matrix
- publish runs output to fill (perf, cost) into matrix cells
- can continue to work on existing problem
- can request the platform to run agent against problems
