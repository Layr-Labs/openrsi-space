# ECDSA challenge assets

This package owns the blank candidate, neutral Rust SDK and progressive
correctness stages (1, 64, 512, then the authoritative `NUM_TESTS` stage).
The generic scaffold manifest declares files and exact-match text edits;
Dungeness contains no Rust source transformations or ECDSA shot counts.

Catalyst installs these trusted assets into each disposable runtime and commits
them with the generated run inputs. Harness source cannot select preparation
code. Changes to grading behavior require a separate challenge-version review.
