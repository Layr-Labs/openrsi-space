"""Public harness discovery and checksummed downloads; no solver login required."""
import json
import os
from pathlib import Path
import re
from urllib.parse import urlencode, urlsplit

from catalyst.common import CatalystError
from catalyst.contracts.results import evaluation_id
from catalyst.client.transport import fetch

PROTOCOL = "catalyst-harness-catalog-v1"
SHA = re.compile(r"[0-9a-f]{64}")


class PublicCatalog:
    def __init__(self, base=None):
        self.base = (base or os.environ.get("CATALYST_EVALUATOR_URL") or "https://3.21.93.126").rstrip("/")
        parts = urlsplit(self.base)
        if (parts.username or parts.password or parts.query or parts.fragment or parts.path
                or not parts.hostname or (parts.scheme != "https" and not (
                    parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}))):
            raise CatalystError("Configure a trusted HTTPS evaluator origin.")

    def get(self, route):
        return json.loads(fetch(self.base + route, ""))

    def search(self, *, source=None, **filters):
        if source is not None and not SHA.fullmatch(source):
            raise CatalystError("Harness source identity must be a SHA-256 hash.")
        route = "/public/harnesses" + (f"/{source}" if source else "")
        query = urlencode({k: v for k, v in filters.items() if v is not None})
        data = self.get(route + ("?" + query if query else ""))
        if data.get("protocol") != PROTOCOL or not isinstance(data.get("items"), list):
            raise CatalystError("Invalid harness catalog response.")
        return data

    def current_problem(self):
        from catalyst.challenge.catalog import PROBLEM_RELEASES, initial_problems
        from catalyst.contracts.results import digest
        data = self.search(limit=1)
        version = data.get("problem_version")
        versions = data.get("problem_versions")
        if not isinstance(version, str) or not SHA.fullmatch(version) or not isinstance(versions, list):
            raise CatalystError("Evaluator did not advertise its active problem version.")
        matches = [p for p in versions if isinstance(p, dict) and p.get("version") == version]
        if len(matches) != 1 or matches[0].get("id") != "ecdsa.fail":
            raise CatalystError("Evaluator returned an invalid active problem binding.")
        release = matches[0].get("release")
        installed = release in PROBLEM_RELEASES and digest(initial_problems(release=release)) == version
        return {"evaluator": self.base, "problem": matches[0], "installed": installed,
                "instruction": "Use this exact release for new local and remote runs. Recheck before submission; never relabel a saved request or receipt."}

    def download(self, identity, output, *, source_sha256=None):
        identity = evaluation_id(identity)
        route = f"/public/evaluations/{identity}/artifacts"
        manifest = self.get(route)
        if (manifest.get("protocol") != "catalyst-artifacts-v1" or manifest.get("evaluation_id") != identity
                or manifest.get("sharing", {}).get("harness") is not True
                or not SHA.fullmatch(manifest.get("source_digest", ""))
                or (source_sha256 is not None and manifest["source_digest"] != source_sha256)):
            raise CatalystError("Public harness does not match the requested source.")
        expected = manifest["artifacts"]["harness"]
        descriptor = self.get(route + "/harness")
        if any(descriptor.get(k) != expected.get(k) for k in ("sha256", "bytes", "media_type")):
            raise CatalystError("Download descriptor does not match the public manifest.")
        size, sha = descriptor["bytes"], descriptor["sha256"]
        if (type(size) is not int or not 0 < size <= 512 * 1024 * 1024
                or not isinstance(sha, str) or not SHA.fullmatch(sha)
                or descriptor["media_type"] != "application/zip"):
            raise CatalystError("Invalid public harness size or checksum.")
        url = descriptor["url"]
        if url == route + "/harness/content":
            url = self.base + url
        else:
            parts = urlsplit(url)
            if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.fragment:
                raise CatalystError("Object downloads require HTTPS.")
        fetch(url, "", output=output, limit=size, expected_size=size, expected_sha256=sha)
        return {"evaluation_id": identity, "source_sha256": manifest["source_digest"],
                "sha256": sha, "bytes": size, "path": str(Path(output).resolve())}
