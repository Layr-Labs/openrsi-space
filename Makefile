.PHONY: check

check:
	uv run --locked python script/check.py
