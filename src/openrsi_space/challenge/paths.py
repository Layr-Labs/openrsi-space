"""Paths to challenge content installed with the public OpenRSI package."""
from pathlib import Path

PROBLEM_SET = Path(__file__).resolve().parents[1] / "problem-set"

# Trusted package directories; never selected from submitted source.
PROBLEM_DIRECTORIES = {"ecdsa.fail": PROBLEM_SET / "ecdsa-fail"}
