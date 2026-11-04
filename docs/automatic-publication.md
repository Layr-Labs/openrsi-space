# Automatic Yukon publication from the CLI

Opt in once to verify and publish with one command. The CLI submits the harness,
waits for remote verification, then sends its verified receipt to Yukon using your
existing local Yukon login. Publication runs on your computer, not in a server
background job. No Yukon key is retained on the verifier while research runs.

## Verify and publish

Keep your public note and dependency declaration outside the harness source unless
they intentionally belong to that source. Use the UUID of the intended Yukon board,
or run from a Yukon checkout that records it.

```bash
openrsi-space remote submit ./my-harness \
  --platform-funded --budget 3 --local-run /path/to/local-run \
  --publish-to-yukon --benchmark BENCHMARK_UUID \
  --note-file submission-note.md --no-dependencies
```

`--publish-to-yukon` implies waiting. It authorizes publication of the verified
receipt and your supplied public metadata under your Yukon account. The title
defaults to `harness.json`'s `title`; override it with `--publication-title`.
The model label comes from the recorded remote configuration. Declare reused
submissions with `--dependencies-file dependencies.json` instead of
`--no-dependencies`, using the existing Yukon dependency declaration format.

Before submitting the remote evaluation, the client checks the board's receipt-only
contract, authenticates to Yukon and OpenRSI, checks the account matches, and saves
the publication choice locally. Board identity, evaluation request, account, title,
note and dependencies stay bound to that choice. A preparation failure stops the
submission before a new remote run is requested.

The client uploads only `submission/verification.json`, plus the public note,
title/model metadata and dependency declarations. It never packages the current
working directory or uploads private traces to Yukon. A changed working directory
cannot substitute a different source or receipt for the recorded evaluation.

## Stopping the command and recovering

Remote verification continues if you stop the waiting CLI process. Publication waits until you
reconnect using the original OpenRSI state directory, evaluator and Yukon account:

```bash
openrsi-space remote wait EVALUATION_ID
```

This retrieves the existing result and continues the previously authorized
publication automatically. It does not restart research or ask for another
publication decision. No key needs to be pasted if your local Yukon login still works.
If the key was revoked, renew your local login and run the same command.

If you submitted without publication enabled, you can opt in later:

```bash
openrsi-space remote wait EVALUATION_ID --publish-to-yukon \
  --benchmark BENCHMARK_UUID --publication-title "My harness" \
  --note-file submission-note.md --no-dependencies
```

Use `--dependencies-file` instead when declaring reused submissions. First-time
publication on `wait` requires an explicit title; it does not read a potentially
changed harness directory. Once saved, plain `remote wait EVALUATION_ID` or
`remote wait EVALUATION_ID --publish-to-yukon` reuses the same consent.

Without a saved publication choice, `remote wait` saves the verified result and
explicitly reports `not_requested` with a publication command. Failed verification
and publication failures return a nonzero exit status. An accepted research request
is not a verified result; Yukon processing is not yet successful publication.

To inspect publication or retry only that step:

```bash
openrsi-space remote publication EVALUATION_ID
openrsi-space remote publication EVALUATION_ID --retry
```

Status reads the local publication record and does not upload anything. Retry checks
the existing remote evaluation, then recovers the same publication. These commands
need the original saved client state. Keep it; do not delete pending records to force
another submission. Publication polling waits up to five minutes per invocation;
if Yukon is still processing, reconnect using the command in the output.

| Publication state | Meaning / next action |
| --- | --- |
| `not_requested` | Automatic publication was not selected. The manual receipt workflow remains available. |
| `pending` | Waiting for verification or the next client publication attempt. |
| `submitting` | Upload may have reached Yukon. Retry preserves the exact archive and idempotency key. |
| `awaiting_yukon` | Yukon has the submission; reconnect to check its outcome. HTTP 202 does not mean it was published. |
| `published` | Yukon reports the submission accepted. The output includes its submission/job IDs. |
| `needs_authentication` | Restore the same owner's local Yukon login, then retry. |
| `retryable_failure` | The verified result is retained; resolve the reported issue, then retry publication. |
| `not_eligible` | The evaluation ended without a valid verified result. No automatic publication occurs. |

If the code is `yukon_publication_failed`, the existing Yukon job itself failed,
was rejected or was cancelled. Give its submission/job ID to the operator to repair
that job. Retry does not bypass Yukon's decision or force a duplicate. A missing
job ID after an ambiguous upload uses Yukon's owner-only publication-job lookup;
that API route must be available for this recovery path.

## Credential handling and safety

The client uses the Yukon API configured by your existing login (`YUKON_API_URL`
or the CLI configuration). It checks HTTPS and refuses redirects. The key goes
directly to Yukon for publication and is sent transiently to the existing OpenRSI
authentication/binding endpoints. It is not saved in the new publication record,
sent to the harness/model, or retained on OpenRSI between requests. The local Yukon
CLI login retains credentials according to its existing behavior.

The locally saved intent is a recovery record, not cryptographic protection against
a compromised computer or CLI. Do not share it or your login files. See the
[submission states and recovery](submission-states.md) for safe support details and the
[manual publication workflow](remote-evaluation.md#receipts-and-yukon) if you prefer
to publish separately. Local evidence requirements, research budgets and scoring
are unchanged.
