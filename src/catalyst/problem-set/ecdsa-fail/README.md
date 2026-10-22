# ECDSA challenge

- `description.md`: the problem statement served to each run.
- `releases/unversioned.json`: the retained production problem and execution contract.
- `knowledge-base/v1.json`: the 50-paper catalog, identified as `ecdsa-papers-v1`.
- `scaffolds/`: the blank candidate and trusted neutral Rust SDK.
- `verifiers/`: version-compatible grading bundles.
- `runtime-assets.json`: maps stable Dungeness destination paths to these assets.
- `historical/`: reference records from the original Dungeness starter workflow.

Only the assigned scaffold and verifier are installed into each disposable runtime.
Catalyst generates current task and run records from the selected release; it does
not install the historical records. The private service adds isolation and source
screening. Changes to grading behavior require a separate challenge-version review.
