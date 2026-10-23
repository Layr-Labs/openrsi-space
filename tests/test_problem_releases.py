import hashlib
from pathlib import Path
import tempfile
import unittest

from catalyst.common import CatalystError, canonical
from catalyst.challenge.papers import load_catalog
from catalyst.challenge.catalog import get_problem, initial_problems, is_official_problem_set
from catalyst.challenge.paths import PROBLEM_SET
from catalyst.cli import build_parser
from catalyst.remote import request_body
from harness_fixture import create_harness


class ProblemReleaseTests(unittest.TestCase):
    def test_launch_v1_has_the_complete_bundled_library(self):
        # Operator-requested eight-paper replacement retains the human tag v1.
        expected = {
            "releases/v1.json": "f526ae84a746fb8c0d6871b28492425b1e046c6e2432d7f6f1111ee8733bf3af",
            "description.md": "192fa7a23e5daed5ab8009135120fc8a94704420676c0c1d955211cf517d6a02",
            "knowledge-base/v1.json": "73153a6bc42f62535c9828fd44a589e5cde8f406c421dccc1b87b74f9dd07460",
        }
        for relative, digest in expected.items():
            self.assertEqual(hashlib.sha256((PROBLEM_SET / "ecdsa-fail" / relative).read_bytes()).hexdigest(), digest)
        problem = get_problem("ecdsa.fail", release="v1")
        self.assertEqual(get_problem("ecdsa.fail"), get_problem("ecdsa.fail", release="v1"))
        catalog = load_catalog(problem["dungeness"]["knowledge_base"])
        self.assertEqual((catalog["count"], len(catalog["papers"])), (8, 8))
        self.assertEqual(problem["dungeness"]["knowledge_base"]["sha256"], hashlib.sha256(canonical(catalog)).hexdigest())
        self.assertEqual({p.name for p in PROBLEM_SET.iterdir()}, {"README.md", "ecdsa-fail"})
        self.assertFalse(list(PROBLEM_SET.rglob("*v0*")))

    def test_only_active_release_is_official(self):
        manifest = initial_problems(release="v1")
        self.assertTrue(is_official_problem_set(manifest))
        manifest[0]["release"] = "v0"
        self.assertFalse(is_official_problem_set(manifest))
        self.assertFalse((PROBLEM_SET / "ecdsa-fail/releases/v2.json").exists())
        for release in ("v0", "v2", "v3", "../initial", ""):
            with self.subTest(release=release), self.assertRaises(CatalystError):
                initial_problems(release=release)
        for binding in ({"id": "../ecdsa-papers-v1"}, {"id": "ecdsa-papers-v0", "sha256": "0" * 64}):
            with self.assertRaises(CatalystError):
                load_catalog(binding)

    def test_remote_request_accepts_v1_and_rejects_retired_release(self):
        with tempfile.TemporaryDirectory() as folder:
            harness = Path(folder) / "harness"
            create_harness(harness)
            for release in (None, "v1"):
                body = request_body(harness, "https://verifier.example.test", problem_release=release)
                self.assertEqual(body["problem_set"], initial_problems(release=release or "v1"))
            with self.assertRaisesRegex(CatalystError, "retired"):
                request_body(harness, "https://verifier.example.test", problem_release="v0")

    def test_cli_only_advertises_active_release(self):
        parser, _ = build_parser()
        for command in (["problem", "show", "ecdsa.fail"],
                        ["local", "run", "harness", "--dungeness", "runtime"],
                        ["remote", "submit", "harness"]):
            self.assertEqual(parser.parse_args([*command, "--problem-release", "v1"]).problem_release, "v1")
            with self.assertRaises(SystemExit):
                parser.parse_args([*command, "--problem-release", "v2"])
            with self.assertRaises(SystemExit):
                parser.parse_args([*command, "--problem-release", "v0"])
