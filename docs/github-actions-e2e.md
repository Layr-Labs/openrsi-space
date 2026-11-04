# Publish a verified result to Yukon

Yukon publishes the result of an existing OpenRSI evaluation. Its receipt check
does not build your harness or start another paid research run.

## Workflow

1. Test the harness locally and submit it for an official remote evaluation.
2. Retrieve the complete service-issued `verification.json` after verification.
3. Copy it unchanged to `submission/verification.json` in the intended Yukon
   benchmark checkout.
4. Run `yukon run` to check the receipt, then use `openrsi-space yukon-submit`
   with your methodology note, harness/model attribution and dependencies.
5. Inspect the Yukon submission/job to confirm publication. An OpenRSI completed
   evaluation or public source download alone does not mean Yukon accepted it.

See the [solver guide](solver-guide.md#6-publish-to-yukon) for the complete commands
and current-client setup. Publish from the same Yukon account that owns the
remote evaluation, using the correct board and evaluator environment.

## Solver commands

Use `openrsi-space yukon-submit` for the normal flow. If Yukon accepted a
submission but its binding step failed, preserve the submission and pending
state; `openrsi-space yukon-bind` can complete the binding without another
research run. Do not submit a second evaluation just to recover publication.

Keep the original receipt, note and IDs until publication is confirmed. Do not
edit a receipt's source, problem, policy, owner or score information. Receipts
for another account or benchmark are not interchangeable.

## Authentication and failures

Your Yukon login identifies you. The hosted workflow authenticates separately;
you do not need to supply it with a model key or server credential. It retrieves
the verified result rather than accepting a score from your note or local files.

If the evaluator is unavailable or rejects publication, retain the error and
submission ID and contact support. A publication failure does not invalidate an
existing verified evaluation or require paying for another one. For an old-board
submission, follow [publication recovery](verifier-endpoint.md#recover-a-publication-sent-to-the-historical-board).

Historical receipts retain their original problem and scoring policy. Changing a
GitHub remote or updating the submission client does not change the board pinned
in a Yukon checkout. Select the intended board explicitly.
