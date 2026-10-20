"""Mint the public gateway placeholder. The real provider credential stays in the gateway."""
import json

print(json.dumps({"access_token": "testbed", "expires_in": 3600}), flush=True)
