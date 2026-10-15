# Codex harness for arXiv:2606.02235

A ready-to-package ECDSA research harness using André Schrottenloher's
*Optimized Point Addition Circuits for Elliptic Curve Discrete Logarithms*.
The unmodified v1 PDF is bundled into the container as Codex's knowledge base,
with attribution and a checksum. There is no extracted text or prepared summary.
Codex reads and interprets the paper during the run; `pdftotext` and `pdftoppm`
are installed for that purpose. No paper download is needed during research.

Codex establishes a baseline, chooses a paper-inspired change, checks it with
Dungeness's evaluator and retains the best passing candidate by
`avg_toffoli × peak_qubits`. This prepares an autonomous research run; it does
not contain a completed implementation of the paper or guarantee an improvement.
The configured $3 budget favors a small experiment. Codex chooses the approach
after reading the paper and inspecting the actual circuit.

Defaults in `evaluation.json`:

- Provider: ChatGPT through Dungeness's native Codex route.
- Model: `gpt-6-astra`, high reasoning effort; Codex CLI 0.153.3.
- Cap: $3 normalized model credits, 1,000,000 tokens, 900 seconds.

Change `max_model_credits` and, for longer experiments, `limits.max_seconds`
before submitting. The prompt uses the configured budget and targets an 85%
soft stop. Dungeness accounts for usage between responses, so a final response
can cross the cap; the current scoring contract rejects over-cap results.
Subscription credits do not necessarily represent a cash charge.

Local checks, without a model call:

```sh
.venv/bin/python harnesses/ecdsa-paper-2606-02235/agent.py --check-references
.venv/bin/python -m unittest discover -s tests -p test_paper_harness.py
.venv/bin/catalyst harness build harnesses/ecdsa-paper-2606-02235
```

When you choose to run it, use your Yukon dev login and local Codex ChatGPT
login. From the Catalyst repository:

```sh
export YUKON_API_URL=https://api-dev.yukon.org
export CATALYST_EVALUATOR_URL=https://3.21.93.126
.venv/bin/catalyst remote submit harnesses/ecdsa-paper-2606-02235 \
  --codex-auth-file --wait
```

That command starts the remote evaluation and consumes model credits. It is
separate from Yukon submission. After success, the receipt is written to this
harness directory's `verification.json`. Copy that receipt to
`submission/verification.json` in your Yukon benchmark checkout and follow the
normal Yukon run/submit flow.

Renewable credentials stay local; temporary access goes over HTTPS and the
launcher stages it in RAM, cleaning up its temporary Codex home on exit.
No credentials belong in this directory. See
[credential handling](../../docs/live-models.md) and
[paper attribution](references/NOTICE.md).
