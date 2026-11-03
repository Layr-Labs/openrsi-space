#!/usr/bin/env bash
set -euo pipefail

install -d -m 0700 /logs/verifier
exec python3 /tests/grade.py
