import hashlib
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from catalyst.problems import get_problem, problem_statement
from catalyst.runtime import launch, problem_server


def fixture():
    document = {
        "schema_version": 1, "run_id": "test-run",
        "problem": {"id": "ecdsa.fail", "version": "a" * 64},
        "statement": "Solve the trusted problem.",
        "candidate_paths": ["src/point_add"],
    }
    payload = problem_server.canonical(document)
    digest = hashlib.sha256(payload).hexdigest()
    task = {
        "problem": document["problem"], "candidate_paths": document["candidate_paths"],
        "instruction": "Research method supplied by the harness.",
        "problem_service": {"url": "http://gateway:8080/task", "sha256": digest},
    }
    return document, payload, digest, task


class ProblemServiceTests(unittest.TestCase):
    def test_files_serve_only_pinned_names_and_reject_mutated_startup_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b"%PDF-1.4\nfixture\n%%EOF"
            paper = root / "paper.pdf"
            paper.write_bytes(raw)
            entry = {"name": "paper.pdf", "bytes": len(raw),
                     "sha256": hashlib.sha256(raw).hexdigest(), "media_type": "application/pdf"}
            payload = problem_server.canonical({"schema_version": 1, "attachments": [entry]})
            files = problem_server.load_files(payload, root)
            with ThreadingHTTPServer(("127.0.0.1", 0),
                                     problem_server.handler_for(payload, "a" * 64, files)) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{server.server_port}"
                try:
                    with urlopen(base + "/task/files/paper.pdf") as response:
                        self.assertEqual(response.read(), raw)
                        self.assertEqual(response.headers["Content-Type"], "application/pdf")
                    for target in ("/task/files/paper.pdf?url=x", "/task/files/../task.json",
                                   "/task/files/unknown.pdf"):
                        with self.assertRaises(HTTPError) as error:
                            urlopen(base + target)
                        self.assertEqual(error.exception.code, 404)
                        error.exception.close()
                finally:
                    server.shutdown()
                    thread.join()
            paper.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                problem_server.load_files(payload, root)

    def test_read_only_server_serves_only_its_startup_snapshot(self):
        document, payload, digest, _ = fixture()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "task.json"
            path.write_bytes(payload)
            loaded = problem_server.load_document(path, digest)
            path.write_text('{"statement":"changed later"}')
            with ThreadingHTTPServer(("127.0.0.1", 0), problem_server.handler_for(loaded, digest)) as server:
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{server.server_port}"
                try:
                    with urlopen(base + "/task") as response:
                        self.assertEqual(json.load(response), document)
                        self.assertEqual(response.headers["X-Task-SHA256"], digest)
                    for method, target, status in (
                        ("POST", "/task", 405), ("DELETE", "/task", 405),
                        ("GET", "/task?problem=other", 404), ("GET", "/../../etc/passwd", 404),
                    ):
                        with self.assertRaises(HTTPError) as error:
                            urlopen(Request(base + target, method=method))
                        self.assertEqual(error.exception.code, status)
                        error.exception.close()
                finally:
                    server.shutdown()
                    thread.join()

    def test_document_must_match_pin_and_fit_limit(self):
        _, payload, digest, _ = fixture()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "task.json"
            for data in (payload.replace(b"trusted", b"forged"), b" " * (256 * 1024 + 1)):
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    problem_server.load_document(path, digest)

    def test_launcher_hydrates_statement_before_starting_harness(self):
        document, payload, _, task = fixture()
        task["workspace"] = "/workspace/repo"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "input.json").write_text(json.dumps(task))
            (root / "execution.json").write_text(json.dumps({"entrypoint": ["python3", "agent.py"]}))
            with patch.object(launch, "build_opener") as opener, patch.object(launch.subprocess, "run") as run:
                opener.return_value.open.return_value = io.BytesIO(payload)
                run.return_value.returncode = 0
                self.assertEqual(launch.launch(root / "input.json", root / "execution.json"), 0)
                args = run.call_args.kwargs
                resolved = json.loads(Path(args["env"]["CATALYST_TASK"]).read_text())
                self.assertEqual(resolved["problem_document"], document)
                self.assertTrue(resolved["instruction"].startswith(document["statement"]))
                self.assertIn(task["instruction"], resolved["instruction"])
                self.assertEqual(args["env"]["CATALYST_PROBLEM_URL"], "http://gateway:8080/task")

    def test_wrong_document_or_endpoint_prevents_harness_launch(self):
        _, payload, _, task = fixture()
        with patch.object(launch, "build_opener") as opener:
            opener.return_value.open.return_value = io.BytesIO(payload.replace(b"trusted", b"forged"))
            with self.assertRaisesRegex(ValueError, "does not match"):
                launch.hydrate_problem(task)
            task["problem_service"]["url"] = "http://attacker.invalid/task"
            with self.assertRaisesRegex(ValueError, "Invalid assigned"):
                launch.hydrate_problem(task)
            self.assertEqual(opener.return_value.open.call_count, 1)

    def test_launcher_exposes_versioned_discovery_without_changing_task_binding(self):
        document, _, _, task = fixture()
        document.update(release="v1", slug="ecdsa-fail",
                        description_url="http://gateway:8080/ecdsa-fail/v1/description",
                        knowledge_base={"url": "http://gateway:8080/ecdsa-fail/v1/knowledge-base", "count": 2})
        payload = problem_server.canonical(document)
        task['problem_service']['sha256'] = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            task['workspace'] = str(root)
            (root / 'task.json').write_text(json.dumps(task))
            (root / 'execution.json').write_text(json.dumps({'entrypoint': ['true']}))
            with patch.object(launch, 'build_opener') as opener, patch.object(launch.subprocess, 'run') as run:
                opener.return_value.open.return_value = io.BytesIO(payload)
                run.return_value.returncode = 0
                launch.launch(root / 'task.json', root / 'execution.json')
                env = run.call_args.kwargs['env']
                self.assertEqual(env['CATALYST_PROBLEM_RELEASE'], 'v1')
                self.assertEqual(env['CATALYST_DESCRIPTION_URL'], document['description_url'])
                self.assertEqual(env['CATALYST_KNOWLEDGE_BASE_URL'], document['knowledge_base']['url'])
                hydrated = json.loads(Path(env['CATALYST_TASK']).read_text())
                self.assertIn('2 resources', hydrated['instruction'])
                self.assertIn('Assigned problem release: v1', hydrated['instruction'])
                self.assertIn(document['description_url'], hydrated['instruction'])
                self.assertIn(document['knowledge_base']['url'], hydrated['instruction'])
                self.assertIn("catalog's resources array", hydrated['instruction'])
                self.assertIn('media_type', hydrated['instruction'])

    def test_invalid_binding_is_rejected_before_network(self):
        _, _, _, task = fixture()
        for service in (
            {"url": "http://gateway:8080/task", "sha256": None},
            {"url": "http://gateway:8080/task", "sha256": "not-a-digest"},
            {"url": "http://gateway:8080/task?problem=other", "sha256": "a" * 64},
            {"url": "http://gateway:8080/task", "sha256": "a" * 64, "token": "secret"},
        ):
            with self.subTest(service=service), patch.object(launch, "build_opener") as opener:
                with self.assertRaisesRegex(ValueError, "Invalid assigned"):
                    launch.hydrate_problem({**task, "problem_service": service})
                opener.assert_not_called()

    def test_valid_digest_cannot_bind_wrong_problem_or_candidate_paths(self):
        document, _, _, task = fixture()
        for change in (
            {"problem": {"id": "different-problem", "version": "a" * 64}},
            {"problem": {"id": "ecdsa.fail", "version": "b" * 64}},
            {"candidate_paths": ["trusted-verifier"]},
            {"schema_version": 2},
            {"statement": None},
        ):
            payload = problem_server.canonical({**document, **change})
            assigned = {**task, "problem_service": {
                "url": "http://gateway:8080/task",
                "sha256": hashlib.sha256(payload).hexdigest(),
            }}
            with self.subTest(change=change), patch.object(launch, "build_opener") as opener:
                opener.return_value.open.return_value = io.BytesIO(payload)
                with self.assertRaisesRegex(ValueError, "identity or candidate paths"):
                    launch.hydrate_problem(assigned)

    def test_unavailable_malformed_or_oversized_document_stops_startup(self):
        _, _, _, task = fixture()
        for payload in (b"null", b"[]", b"invalid json", b" " * (256 * 1024 + 1)):
            with self.subTest(payload=payload[:20]), patch.object(launch, "build_opener") as opener:
                opener.return_value.open.return_value = io.BytesIO(payload)
                with self.assertRaises(ValueError):
                    launch.hydrate_problem(task)
        with patch.object(launch, "build_opener") as opener:
            opener.return_value.open.side_effect = TimeoutError("service unavailable")
            with self.assertRaises(TimeoutError):
                launch.hydrate_problem(task)

    def test_legacy_input_and_public_statement_are_available(self):
        old = {"instruction": "Legacy pinned task."}
        self.assertIs(launch.hydrate_problem(old), old)
        self.assertIn("pub fn build() -> Vec<Op>", problem_statement("ecdsa.fail"))
        self.assertEqual(get_problem("ecdsa.fail")["repository"]["commit"],
                         "62ae3d00d1e01d7bc640b5163cfea8dabffd8392")
