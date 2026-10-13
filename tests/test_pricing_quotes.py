"""Dynamic prices are service evidence, not rates authored by the solver."""
import base64
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from email.message import Message
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from catalyst.common import CatalystError, canonical, open_bundle, read_json, write_json
from catalyst.evaluator import APIError, JobStore, handler_for, validate_request
from catalyst.pricing import CATALOG_URL, PricingQuotes, catalog_entry, fetch_catalog, rate
from catalyst.remote import RemoteClient, digest, judgment, request_body, verification_reference, private_json
from catalyst.tiers import credits, pricing_digest

MODEL = {"provider": "openrouter", "name": "example/new-model"}
OPTIONS = {"provider": MODEL["provider"], "model": MODEL["name"], "budget": 3}
EXECUTION = {"interface": "catalyst-exec-v1", "dockerfile": "Dockerfile",
             "entrypoint": ["python3", "/agent/start.py"]}
CATALOG = {"data": [{
    "id": MODEL["name"], "canonical_slug": "example/new-model-2026",
    "pricing": {"prompt": "0.000002", "completion": "0.000006", "request": "0",
                "input_cache_read": "0.0000002", "input_cache_write": "0.000003"},
}]}


class PricingQuoteTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "existing-repo"
        self.source.mkdir()
        (self.source / "Dockerfile").write_text("FROM python:3.12-slim\nCOPY . /agent/\n")
        (self.source / "start.py").write_text("print('arbitrary source fixture')\n")
        (self.source / "references").mkdir()
        (self.source / "references/notes.txt").write_text("a private knowledge base")
        self.store = JobStore(self.root / "server")
        self.calls = 0

        def fetcher():
            self.calls += 1
            return copy.deepcopy(CATALOG)
        self.quotes = PricingQuotes(self.store, fetcher)
        environment = patch.dict(os.environ, {
            "CATALYST_LOCAL_TEST": "", "CATALYST_LOCAL_ECDSA": "", "GITHUB_ACTIONS": "",
            "CATALYST_EVALUATOR_URL": "https://evaluator.invalid",
        })
        environment.start()
        self.addCleanup(environment.stop)

    def request(self, schedule):
        return {**request_body(self.source, "https://evaluator.invalid", execution=EXECUTION,
                               evaluation_overrides=OPTIONS, pricing=schedule),
                "request_id": str(uuid.uuid4())}

    def test_new_model_price_conversion_and_retained_source_identity(self):
        schedule = self.quotes.issue([MODEL])
        request = self.request(schedule)
        validate_request(request, request["problem_set"], evidence_mode="remote",
                         pricing_validator=self.quotes.validate)
        snapshot, files = open_bundle(base64.b64decode(request["source"]["archive_base64"]))
        self.assertIn("references/notes.txt", files)
        self.assertEqual(snapshot["document"]["execution"], EXECUTION)
        self.assertFalse((self.source / "harness.json").exists())
        usage = {"input_tokens": 1000, "output_tokens": 100, "cached_read_tokens": 200, "cache_write_tokens": 100}
        self.assertEqual(credits(usage, MODEL, schedule), Decimal(".00234"))
        self.assertEqual(self.calls, 1)
        self.quotes.issue([MODEL])
        self.assertEqual(self.calls, 1)  # Bounded public-catalog refresh, not one fetch per request.
        self.assertEqual(read_json(self.root / "server/pricing" / (digest(schedule) + ".json")), schedule)

    def test_solver_cannot_edit_prices_or_use_another_services_quote(self):
        schedule = self.quotes.issue([MODEL])
        changed = copy.deepcopy(schedule)
        changed["entries"][0]["input_per_mtok"] = 0
        for candidate in (changed, {**schedule, "issued_at": "forged"}):
            with self.subTest(candidate=candidate), self.assertRaisesRegex(CatalystError, "not issued"):
                self.quotes.validate(self.request(candidate))
        other = PricingQuotes(JobStore(self.root / "other-server"), lambda: CATALOG)
        with self.assertRaisesRegex(CatalystError, "not issued"):
            other.validate(self.request(schedule))

    def expired_quote(self):
        earlier = datetime.now(timezone.utc) - timedelta(hours=2)
        with patch("catalyst.pricing.datetime") as clock:
            clock.now.return_value = earlier
            return self.quotes.issue([MODEL])

    def test_expiry_rejects_new_jobs_but_exact_accepted_retry_and_history_survive(self):
        schedule = self.expired_quote()
        request = self.request(schedule)
        with self.assertRaises(APIError) as expired:
            self.quotes.validate(request, owner="solver")
        self.assertEqual(expired.exception.status, 410)
        self.store.create("solver", request)
        PricingQuotes(self.store).validate(request, owner="solver")
        PricingQuotes(self.store).validate(request, historical=True)
        changed = copy.deepcopy(request)
        changed["evaluation"]["max_model_credits"] = 2
        with self.assertRaises(APIError) as conflict:
            self.quotes.validate(changed, owner="solver")
        self.assertEqual(conflict.exception.status, 409)
        with self.assertRaises(APIError):
            self.quotes.validate(request, owner="another-solver")

    def test_catalog_cannot_supply_invalid_rates_unknown_charges_or_ambiguous_identity(self):
        for value in ("NaN", "Infinity", "-1", None, True, {}, "not-a-price"):
            with self.subTest(value=value), self.assertRaises(CatalystError):
                rate(value)
        for field in ("image", "audio", "web_search", "request", "future_unknown_bucket"):
            catalog = copy.deepcopy(CATALOG)
            catalog["data"][0]["pricing"][field] = "0.01"
            with self.subTest(field=field), self.assertRaises(CatalystError):
                catalog_entry(MODEL, catalog)
        with self.assertRaises(CatalystError):
            catalog_entry(MODEL, {"data": CATALOG["data"] * 2})
        with self.assertRaises(CatalystError):
            catalog_entry({"provider": "openrouter", "name": "openrouter/auto"}, CATALOG)

    def test_direct_provider_identity_cannot_claim_an_unrelated_cheaper_model(self):
        model = {"provider": "anthropic", "name": "new-claude"}
        catalog = {"data": [{**CATALOG["data"][0], "id": "anthropic/new-claude"}]}
        self.assertEqual(catalog_entry(model, catalog)["upstream_id"], "anthropic/new-claude")
        with self.assertRaises(CatalystError):
            catalog_entry({"provider": "openai", "name": "new-claude"}, catalog)

    def test_missing_cache_prices_have_explicit_input_rate_reference_fallback(self):
        catalog = copy.deepcopy(CATALOG)
        del catalog["data"][0]["pricing"]["input_cache_read"]
        del catalog["data"][0]["pricing"]["input_cache_write"]
        entry = catalog_entry(MODEL, catalog)
        self.assertEqual(entry["cached_read_per_mtok"], entry["input_per_mtok"])
        self.assertEqual(entry["cache_write_per_mtok"], entry["input_per_mtok"])

    def test_catalog_download_has_fixed_destination_bounded_read_and_private_operator_auth(self):
        class Response(io.BytesIO):
            def read(inner, limit):
                self.assertEqual(limit, 16 * 1024 * 1024 + 1)
                return super().read(limit)

        with patch.dict(os.environ, {"CATALYST_OPENROUTER_CATALOG_TOKEN": "offline-catalog-key"}), \
                patch("catalyst.pricing.build_opener") as opener:
            opener.return_value.open.return_value = Response(canonical(CATALOG))
            self.assertEqual(fetch_catalog(), CATALOG)
            request = opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url, CATALOG_URL)
            self.assertEqual(request.get_header("Authorization"), "Bearer offline-catalog-key")
            self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"], 20)
        self.assertNotIn("offline-catalog-key", canonical(self.quotes.issue([MODEL])).decode())

    def test_catalog_outage_never_produces_zero_cost_quote(self):
        def unavailable():
            raise CatalystError("offline catalog failure")
        quotes = PricingQuotes(self.store, unavailable)
        with self.assertRaises(APIError) as failed:
            quotes.issue([MODEL])
        self.assertEqual(failed.exception.status, 503)
        self.assertFalse(quotes.root.exists())

    def test_client_freezes_quote_on_uncertain_post_and_exports_after_restart(self):
        client = RemoteClient(self.root / "client", bearer="offline-solver-key")
        posts, identities = [], {}
        quote_requests = []
        lose_ack = True

        def transport(base, route, bearer, *, document, **kwargs):
            nonlocal lose_ack
            if route == "/pricing/quote":
                self.assertNotIn("model_token", kwargs)
                quote_requests.append(document)
                return canonical({"pricing": self.quotes.issue(document["models"])})
            self.assertEqual(route, "/evaluations")
            self.assertEqual(kwargs["model_token"], "offline-provider-key")
            self.quotes.validate(document, owner="solver")
            posts.append(document)
            identity = self.store.create("solver", document)
            identities[identity] = document
            if lose_ack:
                lose_ack = False
                raise CatalystError("lost acknowledgement")
            return canonical({"request_id": document["request_id"], "evaluation_id": identity})

        with patch("catalyst.remote.solver_fetch", side_effect=transport):
            with self.assertRaisesRegex(CatalystError, "lost acknowledgement"):
                client.submit(self.source, execution=EXECUTION, evaluation_overrides=OPTIONS,
                              model_token="offline-provider-key")
            accepted = RemoteClient(client.state, bearer="offline-solver-key").submit(
                self.source, execution=EXECUTION, evaluation_overrides=OPTIONS, model_token="offline-provider-key")
        self.assertEqual(posts[0], posts[1])
        self.assertEqual(len(quote_requests), 1)
        self.assertEqual(len(identities), 1)
        identity = accepted["evaluation_id"]
        request = posts[0]
        result = {"evaluation_id": identity, "build": {"image_digest": "sha256:" + "b" * 64}}
        reference = verification_reference(result, request)
        private_json(client.folder(identity) / "verification.json", reference)
        self.assertEqual(read_json(client.export_reference(identity)), reference)
        for path in client.state.rglob("*.json"):
            self.assertNotIn("offline-provider-key", path.read_text())

    def test_client_renews_only_definitively_unaccepted_expired_quote(self):
        from catalyst.remote import HTTPFailure
        client = RemoteClient(self.root / "client", bearer="offline-solver-key")
        quoted, submitted = [], []

        def transport(base, route, bearer, *, document, **kwargs):
            if route == "/pricing/quote":
                schedule = self.expired_quote() if not quoted else self.quotes.issue([MODEL])
                quoted.append(schedule)
                return canonical({"pricing": schedule})
            submitted.append(document)
            try:
                self.quotes.validate(document, owner="solver")
            except APIError as error:
                raise HTTPFailure(error.status) from None
            identity = self.store.create("solver", document)
            return canonical({"request_id": document["request_id"], "evaluation_id": identity})

        with patch("catalyst.remote.solver_fetch", side_effect=transport):
            accepted = client.submit(self.source, execution=EXECUTION, evaluation_overrides=OPTIONS,
                                     model_token="offline-provider-key")
        self.assertEqual(len(quoted), 2)
        self.assertEqual(len(submitted), 2)
        self.assertNotEqual(submitted[0]["pricing"], submitted[1]["pricing"])
        self.assertEqual(self.store.get(accepted["evaluation_id"])["request"], submitted[1])

    def test_pricing_snapshot_drives_actual_ledger_and_public_score(self):
        from catalyst.worker import collect_usage
        from test_yukon import completed
        schedule = self.quotes.issue([MODEL])
        request = self.request(schedule)
        run = self.root / "run"
        (run / "usage").mkdir(parents=True)
        event = {"source": "gateway", "kind": "model.accounting", "request_id": "call-1", "data": {
            "provider": MODEL["provider"], "model": MODEL["name"], "input_tokens": 1000,
            "output_tokens": 100, "cached_input_tokens": 200, "cache_write_input_tokens": 100,
            "normalized_usd": .00234, "accounting_method": "gateway"}}
        (run / "usage/events.jsonl").write_text(json.dumps(event) + "\n")
        write_json(run / "record.json", {"data": {"usage": {"normalized_usd": .00234}}})
        ledger, total = collect_usage(run, request["evaluation"], schedule)
        self.assertEqual(total, Decimal(".00234"))
        result = completed(request, str(uuid.uuid4()))
        observation = result["observations"][0]
        observation.update(pricing_digest=pricing_digest(schedule), normalized_model_usd=float(total),
                           usage=ledger, checkpoints=[])
        observation["curve"][0]["normalized_model_usd"] = float(total)
        artifact = judgment(result, request)
        self.assertEqual(artifact["scores"], [100, .00234])
        with self.assertRaises(CatalystError):
            collect_usage(run, request["evaluation"])

    def test_real_http_handlers_share_quote_trust_without_tcp_listener(self):
        principal = {"kind": "yukon-solver", "owner": "solver"}

        class Auth:
            def authenticate(self, header):
                return principal
            def authorize_run(self, principal, request):
                pass
            def creation_limits(self):
                return None

        class Inbox:
            def enqueue(_, owner, request, limits, token):
                self.assertEqual(token, "offline-provider-key")
                return self.store.create(owner, request)

        with patch("catalyst.pricing.PricingQuotes", return_value=self.quotes):
            handler = handler_for(self.store, Auth(), self.request(self.quotes.issue([MODEL]))["problem_set"],
                                  evidence_mode="remote", credentials=Inbox())

        def call(route, document):
            instance = object.__new__(handler)
            instance.command, instance.path = "POST", route
            payload = canonical(document)
            instance.rfile = io.BytesIO(payload)
            instance.headers = Message()
            instance.headers["Content-Type"] = "application/json"
            instance.headers["Content-Length"] = str(len(payload))
            instance.headers["X-Catalyst-Model-Token"] = "offline-provider-key"
            replies = []
            instance.send = lambda status, value, **kwargs: replies.append((status, value))
            instance.dispatch()
            return replies[0]

        status, quoted = call("/pricing/quote", {"models": [MODEL]})
        self.assertEqual(status, 200)
        status, accepted = call("/evaluations", self.request(quoted["pricing"]))
        self.assertEqual(status, 202)
        self.assertEqual(self.store.get(accepted["evaluation_id"])["status"], "queued")
        forged = self.request(quoted["pricing"])
        forged["pricing"]["entries"][0]["output_per_mtok"] = 0
        self.assertEqual(call("/evaluations", forged)[0], 400)


if __name__ == "__main__":
    unittest.main()
