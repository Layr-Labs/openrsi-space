# ECDSA challenge

- `description.md`: the problem statement served to each run.
- `releases/v1.json`: the launch execution contract and 40-paper library.
- `knowledge-base/v1.json`: retains 35 licensed works, including André
  Schrottenloher's [required paper](https://arxiv.org/abs/2606.02235v1), and adds
  five papers on arithmetic and circuit optimization. Fifteen entries with
  NonCommercial restrictions or no established redistribution license are omitted.
- `knowledge-base/licenses-v1.json`: publisher evidence and selection record.
- `knowledge-base/bundled/`: all 40 unmodified, licensed v1 PDFs (about 52 MB),
  included in the source checkout and Python package for offline preparation.
- `scaffolds/`: the blank candidate and trusted neutral Rust SDK.
- `verifiers/`: version-compatible grading bundles.
- `runtime-assets.json`: maps stable Dungeness destination paths to these assets.
- `historical/`: reference records from the original Dungeness starter workflow.

Only the assigned scaffold and verifier are installed into each disposable runtime.
Catalyst generates current task and run records from the selected release; it does
not install the historical records. The private service adds isolation and source
screening. Changes to grading behavior require a separate challenge-version review.

Use `catalyst problem current` to confirm the evaluator's assigned release before
preparing a new run. The package defaults to `v1`; pass `--problem-release v1`
explicitly after checking the service. The 40-paper release was renumbered to `v1` before launch; the older 50-paper
selector is removed. Existing requests and receipts retain their exact hashes.

Preparation checks each PDF's size and SHA-256, using an existing cache, then a
bundled copy, then its pinned publisher URL. The complete v1 library is bundled,
so its preparation needs no paper cache or network access. Agents read individual resources
through the problem server; these papers are not inserted into their prompt.
