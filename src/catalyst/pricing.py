"""Service-owned, immutable pricing quotes for newly declared models.

Only the service fetches the fixed public catalog URL. Solver-supplied rates and
arbitrary upstream URLs are never trusted. Existing benchmark pins remain valid.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import threading
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .common import CatalystError, canonical, read_json
from .tiers import evaluation_models, model_prices, pricing_schedule

CATALOG_URL = "https://openrouter.ai/api/v1/models"
MAX_CATALOG_BYTES = 16 * 1024 * 1024
PROVIDER_AUTHORS = {"openai": "openai", "openai-chatgpt": "openai",
                    "anthropic": "anthropic", "moonshot": "moonshotai"}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise CatalystError("Pricing catalog redirects are refused.")


def fetch_catalog():
    try:
        headers = {"Accept": "application/json", "User-Agent": "Catalyst-Pricing/1"}
        token = os.environ.get("CATALYST_OPENROUTER_CATALOG_TOKEN")
        if token:
            if any(ord(c) < 33 or ord(c) > 126 for c in token):
                raise ValueError
            headers["Authorization"] = "Bearer " + token
        request = Request(CATALOG_URL, headers=headers)
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            content = response.read(MAX_CATALOG_BYTES + 1)
        if len(content) > MAX_CATALOG_BYTES:
            raise ValueError
        catalog = json.loads(content)
        if not isinstance(catalog, dict) or not isinstance(catalog.get("data"), list):
            raise ValueError
        return catalog
    except (OSError, ValueError):
        raise CatalystError("OpenRouter pricing is unavailable; no evaluation was started.") from None


def rate(value):
    try:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError
        parsed = Decimal(str(value))
        if not parsed.is_finite() or parsed < 0 or parsed > 1000:
            raise ValueError
        return parsed
    except (InvalidOperation, ValueError):
        raise CatalystError("Catalog contains an invalid or unavailable reference price.") from None


def catalog_entry(model, catalog):
    provider, name = model["provider"], model["name"]
    if provider == "openrouter":
        identity = name
    elif provider in PROVIDER_AUTHORS:
        author = PROVIDER_AUTHORS[provider]
        identity = name if name.startswith(author + "/") else author + "/" + name
    else:
        raise CatalystError("Cannot establish an exact catalog identity for this provider/model.")
    matches = [entry for entry in catalog["data"] if entry.get("id") == identity]
    if len(matches) != 1 or identity == "openrouter/auto":
        raise CatalystError("Declared model has no unique, fixed OpenRouter catalog identity.")
    entry = matches[0]
    prices = entry.get("pricing")
    if not isinstance(prices, dict):
        raise CatalystError("Model has no reference pricing.")
    fields = {"prompt", "completion", "input_cache_read", "input_cache_write"}
    # Extra non-token charges need another measured usage dimension.
    if any(rate(value) != 0 for key, value in prices.items() if key not in fields):
        raise CatalystError("Model has non-token charges that cannot yet be independently metered.")
    prompt, completion = rate(prices.get("prompt")), rate(prices.get("completion"))
    return {
        "provider": provider, "upstream_id": identity, "request_models": [name],
        "input_per_mtok": float(prompt * 1_000_000),
        "output_per_mtok": float(completion * 1_000_000),
        "cached_read_per_mtok": float(rate(prices.get("input_cache_read", str(prompt))) * 1_000_000),
        "cache_write_per_mtok": float(rate(prices.get("input_cache_write", str(prompt))) * 1_000_000),
        "text_only": True,
        "reference": {"id": identity, "canonical_slug": entry.get("canonical_slug"),
                      "pricing": prices},
    }


class PricingQuotes:
    """Quotes survive restarts; only new submissions must use an unexpired quote."""
    def __init__(self, store, fetcher=fetch_catalog):
        self.store, self.fetcher = store, fetcher
        self.root = store.root / "pricing"
        self.lock = threading.Lock()
        self.cached = None
        self.cached_until = None

    def issue(self, models):
        from .remote import validate_model
        if not isinstance(models, list) or not 1 <= len(models) <= 16:
            raise CatalystError("Declare 1..16 models.")
        seen, entries, unknown = set(), [], []
        for model in models:
            validate_model(model, check_pricing=False)
            pair = (model["provider"], model["name"])
            if pair in seen:
                raise CatalystError("Duplicate model declaration.")
            seen.add(pair)
            try:
                entries.append(model_prices(model))
            except CatalystError:
                unknown.append(model)
        if not unknown:
            return pricing_schedule()
        with self.lock:
            clock = datetime.now(timezone.utc)
            if self.cached is None or clock >= self.cached_until:
                try:
                    self.cached = self.fetcher()
                except CatalystError:
                    from .evaluator import APIError
                    raise APIError(503, "Reference pricing catalog is unavailable; no evaluation was started.") from None
                self.cached_until = clock + timedelta(minutes=5)
            catalog = self.cached
            entries.extend(catalog_entry(model, catalog) for model in unknown)
            document = {
                "schema_version": 2, "id": "catalyst-model-credits-quote-v1",
                "unit": "normalized_model_usd", "issued_at": clock.isoformat(),
                "expires_at": (clock + timedelta(hours=1)).isoformat(),
                "source": {"url": CATALOG_URL, "sha256": hashlib.sha256(canonical(catalog)).hexdigest()},
                "policy": "Flat reference token rates; absent cache rates use input rate; text only for catalog entries.",
                "entries": sorted(entries, key=lambda item: (item["provider"], item["upstream_id"])),
            }
            identity = hashlib.sha256(canonical(document)).hexdigest()
            self.root.mkdir(mode=0o700, exist_ok=True)
            target = self.root / (identity + ".json")
            if not target.exists():
                # An exclusive write never replaces an earlier snapshot.
                with target.open("xb") as output:
                    output.write(canonical(document))
            return document

    def validate(self, request, *, owner=None, historical=False):
        schedule = request["pricing"]
        if schedule == pricing_schedule():
            return
        identity = hashlib.sha256(canonical(schedule)).hexdigest()
        path = self.root / (identity + ".json")
        if not path.is_file() or read_json(path) != schedule:
            raise CatalystError("Pricing snapshot was not issued by this service.")
        if not historical and owner is not None:
            with self.store.connect() as db:
                previous = db.execute("SELECT request FROM jobs WHERE owner=? AND request_id=?",
                                      (owner, request.get("request_id"))).fetchone()
            # Retry the exact accepted request without renewing or repricing it.
            if previous and json.loads(previous["request"]) == request:
                return
            if previous:
                from .evaluator import APIError
                raise APIError(409, "Operation key already belongs to another request.")
        if not historical and datetime.now(timezone.utc) >= datetime.fromisoformat(schedule["expires_at"]):
            from .evaluator import APIError
            raise APIError(410, "Unaccepted pricing quote expired; obtain a fresh quote.")
        for model in evaluation_models(request["evaluation"]):
            model_prices(model, schedule)
