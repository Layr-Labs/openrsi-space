import unittest
from pathlib import Path
import tempfile
from types import SimpleNamespace

from catalyst.cheat_filter import screen, require_pass, install_sidecar_screen
from catalyst.common import CatalystError, digest_files


class CheatFilterTests(unittest.TestCase):
    def test_circuit_code_is_accepted_and_bound_to_exact_bytes(self):
        files = {"src/point_add/mod.rs": b'fn build() { let n = std::env::var("WINDOW"); eprintln!("{n:?}"); }'}
        report = screen(files, "candidate")
        require_pass(report)
        self.assertEqual(report["digest"], digest_files(files))
        self.assertEqual(report["findings"], [])

    def test_tampering_and_host_access_are_rejected(self):
        for source in (b'std::fs::write("score.json", "1")',
                       b'use std :: process :: Command;', b'unsafe { execute() }',
                       b'include!("/opt/evaluator/main.rs");',
                       b'const URL: &str = "http://169.254.169.254";',
                       b'use std::net::TcpStream;',
                       b'use std::{fs as disk};',
                       b'use ::std as hidden;',
                       b'use std as hidden; hidden::fs::write("result", "1");',
                       b'std /* disguise */ :: fs :: write("result", "1");',
                       b'use std::r#fs;'):
            with self.subTest(source=source):
                report = screen({"src/point_add/mod.rs": source}, "candidate")
                with self.assertRaises(CatalystError):
                    require_pass(report)

    def test_harness_can_use_processes_but_cannot_embed_credentials(self):
        require_pass(screen({"agent.py": b'import subprocess; subprocess.run(["codex", "exec"])'}, "harness"))
        secret = "ykn_" + "a" * 64
        report = screen({"agent.py": f'token = "{secret}"'.encode()}, "harness")
        self.assertEqual(report["findings"][0]["rule"], "embedded-api-key")
        self.assertNotIn(secret, str(report))
        self.assertNotIn("token =", str(report))

    def test_non_source_candidates_fail_closed(self):
        for files in ({"src/point_add/payload": b"binary"},
                      {"src/point_add/mod.rs": b"\xff"}):
            with self.assertRaises(CatalystError):
                require_pass(screen(files, "candidate"))

    def test_comments_do_not_reject_legitimate_circuit_discussion(self):
        source = b'''// Earlier design was phase-unsafe; don't use std::fs.
/* outer /* unsafe {} */ nested comment */
fn build() { let url = "https://example.org"; }
'''
        require_pass(screen({"mod.rs": source}, "candidate"))
        # Strings cannot disguise actual code as a comment.
        report = screen({"mod.rs": b'let url = r#"https://example.org"#; std::fs::write("x", "y");'}, "candidate")
        self.assertEqual(report["status"], "rejected")
        report = screen({"mod.rs": b"""let quote = '"'; let url = "http://example.org"; std::fs::write("x", "y");"""}, "candidate")
        self.assertEqual(report["status"], "rejected")

    def test_sidecar_gates_each_evaluation_and_keeps_original_grader(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "verifiers/ecdsa-fail/benchmark-sh"
            folder.mkdir(parents=True)
            (folder / "serve.py").write_text('if __name__ == "__main__":\n    pass\n')
            (folder / "Dockerfile").write_text("COPY serve.py /tests/serve.py\n")
            (folder / "grade.py").write_text("original trusted scorer")
            changed = install_sidecar_screen(root)
            self.assertEqual(changed, ["verifiers/ecdsa-fail/benchmark-sh/serve.py"])
            self.assertEqual((folder / "grade.py").read_text(), "original trusted scorer")
            self.assertEqual((folder / "Dockerfile").read_text(), "COPY serve.py /tests/serve.py\n")
            calls = []
            grade = SimpleNamespace(INVALID_SCORE=1e18, score_candidate=lambda path: calls.append(path) or {"status": "ok"})
            namespace = {"__name__": "test_sidecar", "grade": grade}
            exec(compile((folder / "serve.py").read_text(), "serve.py", "exec"), namespace)
            candidate = root / "candidate"
            candidate.mkdir()
            (candidate / "mod.rs").write_text("fn build() {}")
            self.assertEqual(grade.score_candidate(candidate)["status"], "ok")
            (candidate / "mod.rs").write_text('std::fs::write("score.json", "1")')
            self.assertEqual(grade.score_candidate(candidate)["status"], "screen_rejected")
            self.assertEqual(len(calls), 1)
