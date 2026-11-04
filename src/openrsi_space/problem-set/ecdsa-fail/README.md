# ECDSA challenge

- `description.md`: the problem statement served to each run.
- `releases/v1.json`: the execution contract and eight-paper library binding.
- `knowledge-base/v1.json`: the eight raw papers, including André Schrottenloher’s
  [point-addition paper](https://arxiv.org/abs/2606.02235v1).
- `knowledge-base/licenses-v1.json`: publisher evidence and replacement provenance.
- `knowledge-base/bundled/`: all eight unmodified PDFs for offline preparation.
- `scaffolds/`: the blank candidate and trusted neutral Rust SDK.
- `verifiers/`: version-compatible grading bundles.
- `runtime-assets.json`: maps stable Dungeness destination paths to these assets.
- `historical/`: reference records from the original Dungeness starter workflow.

Only the assigned scaffold and verifier are installed into each disposable runtime.
OpenRSI generates current task and run records from the selected release; it does
not install the historical records. Changes to grading behavior require a separate
challenge-version review.

Use `openrsi-space problem current` to confirm the evaluator’s assigned release and exact
hash before preparing a run. The eight-paper collection replaces the prelaunch
40-paper collection under the operator-requested tag `v1`. Existing requests and
receipts retain their original hashes; sharing the tag does not make them equivalent.

Preparation checks each PDF’s size and SHA-256, using a cache, bundled copy, then
its pinned publisher URL. All eight papers are bundled, so preparation needs no
paper cache or network access. Agents read resources interactively through the
problem server; the papers are not inserted into their prompt.
