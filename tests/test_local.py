"""Public local runs share task assembly, without hosted access or credentials in evidence."""
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from catalyst import local
from catalyst.cli import main
from catalyst.common import snapshot_directory, read_json, write_json
from catalyst.executable import SOURCE_EXCLUDES
from catalyst.problems import get_problem, problem_statement
from catalyst.task_setup import yaml_file


def commit(root):
    for args in (['add', '-A'], ['-c', 'commit.gpgsign=false', '-c', 'user.name=Test',
                 '-c', 'user.email=test@localhost', 'commit', '-qm', 'Local test runtime']):
        subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)


class LocalRunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'runtime'
        self.source.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.source)], check=True)
        for name, content in {
            'dungeness': '#!/usr/bin/env python3\n',
            'src/dungeness/compiler.py': 'def resolve_problem_service(): pass\n',
            'services/gateway/gateway.py': 'async def assigned_task(): pass\n',
            **{'verifiers/ecdsa-fail/benchmark-sh/' + name: 'fixture\n'
               for name in ('Dockerfile', 'grade.py', 'serve.py', 'test.sh', 'evaluator.lock.yaml')},
            'scaffolds/ecdsa-point-add-sdk-v1/scaffold.yaml':
                'schema_version: 1\ntype: scaffold\ncandidate_path: src/point_add\n',
        }.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        commit(self.source)
        self.harness = self.root / 'harness'
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(['harness', 'create', 'local-test', '--executable',
                                   '--output', str(self.harness)]), 0)
        self.state = self.harness / '.catalyst'
        self.out, self.err = io.StringIO(), io.StringIO()
        self.build = patch('catalyst.local.executable.build', side_effect=self.fake_build).start()
        self.addCleanup(patch.stopall)
        patch('catalyst.local.executable.inspect_build').start()
        patch('catalyst.local.shutil.which', return_value='/fake/tool').start()
        patch('catalyst.remote.RemoteClient', side_effect=AssertionError('Hosted API must not be used')).start()

    def fake_build(self, state, path):
        snapshot, _ = snapshot_directory(path, exclude=SOURCE_EXCLUDES)
        return {'id': 'a' * 64, 'source_digest': snapshot['version'],
                'image_id': 'sha256:' + 'b' * 64, 'artifact_tag': 'catalyst-image:' + 'b' * 64}

    def cli(self, *extra, provider='openai', model='gpt-5.6-sol'):
        with redirect_stdout(self.out), redirect_stderr(self.err):
            return main(['--state', str(self.state), 'local', 'run', str(self.harness),
                         '--dungeness', str(self.source), '--provider', provider,
                         '--model', model, '--budget', '1', '--max-seconds', '60', *extra])

    def metadata(self):
        paths = list(self.state.glob('local/*/run.json'))
        self.assertEqual(len(paths), 1)
        return read_json(paths[0])

    def test_prepare_only_builds_self_contained_inputs_without_credentials_or_remote_service(self):
        with patch('catalyst.local.credential_input', side_effect=AssertionError('credentials read')), \
                patch('catalyst.local.execute_process', side_effect=AssertionError('model run')):
            self.assertEqual(self.cli('--prepare-only'), 0, self.err.getvalue())
        metadata = self.metadata()
        self.assertEqual(metadata['status'], 'prepared')
        self.assertFalse(metadata['official'])
        runtime = Path(metadata['runtime'])
        task_path, = runtime.glob('tasks/**/task.yaml')
        task = yaml_file(task_path)
        self.assertEqual(task['resources']['verifier']['memory_mb'], 8192)
        self.assertEqual(read_json(task_path.parent / 'problem-service/task.json')['statement'],
                         problem_statement('ecdsa.fail'))
        spec = yaml_file(Path(metadata['spec_path']))
        self.assertEqual(spec['initialization'], {'mode': 'scaffold'})
        self.assertEqual(task['scaffold'], 'scaffolds/ecdsa-point-add-sdk-v1/scaffold.yaml')
        assigned = read_json(task_path.parent / 'problem-service/task.json')
        self.assertEqual(assigned['initialization'], {'mode': 'scaffold'})
        checkpoint_path, = runtime.glob('checkpoints/catalyst-*/*.yaml')
        self.assertNotIn('reference', yaml_file(checkpoint_path)['data'])
        self.assertEqual(spec['budget']['max_usd'], 1)
        self.assertEqual(spec['model_access']['models'][0]['request_model'], 'gpt-5.6-sol')
        self.assertEqual(local.git(runtime, 'status', '--porcelain'), '')
        self.assertTrue((task_path.parent / 'problem-service/server.py').is_file())
        self.assertFalse((runtime / 'tasks/users').exists())
        self.assertEqual(Path(spec['runtime']['env_file']).read_text(), '')

    def test_local_run_uses_gateway_only_secret_then_removes_it_and_retains_usage(self):
        observed = {}
        def execute(command, runtime, environment):
            env_file = Path(command[command.index('--env-file') + 1])
            observed['path'] = env_file
            self.assertEqual(env_file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(env_file.read_text(), 'TESTBED_OPENAI_API_KEY=synthetic-model-access\n')
            self.assertNotIn('USER_TEST_KEY', environment)
            self.assertIn('--agent-timeout-sec', command)
            self.assertEqual(command[-1], '60')
            metadata = self.metadata()
            write_json(Path(metadata['record_path']), {'data': {
                'usage': {'normalized_usd': 0.25}, 'metrics': {'ecdsafail_score': 12345}}})
            return 0
        with patch.dict(os.environ, {'USER_TEST_KEY': 'synthetic-model-access'}), \
                patch('catalyst.local.execute_process', side_effect=execute):
            self.assertEqual(self.cli('--provider-token-env', 'USER_TEST_KEY'), 0, self.err.getvalue())
        self.assertFalse(observed['path'].exists())
        metadata = self.metadata()
        self.assertEqual(metadata['usage']['normalized_usd'], 0.25)
        self.assertEqual(metadata['metrics']['ecdsafail_score'], 12345)
        self.assertEqual(metadata['status'], 'completed')
        self.assertNotIn('synthetic-model-access', self.out.getvalue() + self.err.getvalue())
        for path in self.state.rglob('*'):
            if path.is_file():
                self.assertNotIn(b'synthetic-model-access', path.read_bytes(), path)
        self.assertFalse(list(self.state.rglob('verification.json')))

    def test_subscription_refresh_stays_local_and_cleanup_survives_failure(self):
        auth = self.root / 'auth.json'
        auth.write_text(json.dumps({'auth_mode': 'chatgpt', 'last_refresh': '2026-10-15T00:00:00Z',
                        'tokens': {'access_token': 'synthetic-access', 'id_token': 'synthetic-id',
                                   'account_id': 'synthetic-account', 'refresh_token': 'NEVER_COPY_REFRESH'}}))
        before = auth.read_bytes()
        seen = {}
        def execute(command, runtime, environment):
            path = Path(environment['DUNGENESS_CODEX_AUTH_FILE'])
            seen['path'] = path
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(read_json(path)['tokens']['access_token'], 'synthetic-access')
            self.assertNotIn('refresh_token', read_json(path)['tokens'])
            return 7
        with patch('catalyst.local.execute_process', side_effect=execute):
            self.assertEqual(self.cli('--codex-auth-file', str(auth), provider='openai-chatgpt',
                                      model='gpt-6-astra'), 7, self.err.getvalue())
        self.assertFalse(seen['path'].exists())
        self.assertEqual(auth.read_bytes(), before)
        self.assertEqual(self.metadata()['status'], 'failed')

    def test_bad_model_and_dirty_runtime_fail_before_build(self):
        self.assertEqual(self.cli('--prepare-only', model='unknown-unpriced-model'), 1)
        self.build.assert_not_called()
        (self.source / 'dungeness').write_text('# changed\n')
        self.assertEqual(self.cli('--prepare-only'), 1)
        self.build.assert_not_called()
        self.assertIn('clean Dungeness checkout', self.err.getvalue())

    def test_missing_or_packaged_credentials_fail_before_build(self):
        self.assertEqual(self.cli(), 1)
        self.assertEqual(self.cli('--prepare-only', '--provider-access-file', str(self.harness / 'keys.json')), 1)
        self.build.assert_not_called()
        self.assertIn('outside the harness', self.err.getvalue())

    def test_interruption_still_removes_temporary_access(self):
        captured = []
        def execute(command, runtime, environment):
            captured.append(Path(command[command.index('--env-file') + 1]))
            raise KeyboardInterrupt
        with patch.dict(os.environ, {'USER_TEST_KEY': 'synthetic-model-access'}), \
                patch('catalyst.local.execute_process', side_effect=execute):
            self.assertEqual(self.cli('--provider-token-env', 'USER_TEST_KEY'), 130)
        self.assertFalse(captured[0].exists())
        self.assertEqual(self.metadata()['status'], 'cancelled')

    def test_ensemble_uses_all_declared_models_and_exact_provider_credentials(self):
        models = [{'provider': 'openai', 'name': 'gpt-5.6-sol'},
                  {'provider': 'kimi-code', 'name': 'k3'}]
        write_json(self.harness / 'evaluation.json', {
            'schema_version': 4, 'llm_access': {'grant_id': 'grant_temporary_provider'},
            'model': models[0], 'models': models, 'max_model_credits': 1,
            'limits': {'max_model_tokens': 1000, 'max_seconds': 60},
        })
        credentials = self.root / 'providers.json'
        write_json(credentials, {'openai': 'synthetic-openai-key', 'kimi-code': 'synthetic-kimi-key'})
        def execute(command, runtime, environment):
            spec = yaml_file(Path(self.metadata()['spec_path']))
            self.assertEqual([m['provider'] for m in spec['model_access']['models']], ['openai', 'kimi-code'])
            contents = Path(command[command.index('--env-file') + 1]).read_text()
            self.assertIn('TESTBED_OPENAI_API_KEY=synthetic-openai-key\n', contents)
            self.assertIn('TESTBED_KIMI_CODE_API_KEY=synthetic-kimi-key\n', contents)
            return 0
        with patch('catalyst.local.execute_process', side_effect=execute), \
                redirect_stdout(self.out), redirect_stderr(self.err):
            self.assertEqual(main(['--state', str(self.state), 'local', 'run', str(self.harness),
                                   '--dungeness', str(self.source),
                                   '--provider-access-file', str(credentials)]), 0, self.err.getvalue())

    @unittest.skipUnless(os.environ.get('CATALYST_DUNGENESS'), 'Requires a real clean Dungeness checkout')
    def test_public_local_package_compiles_with_real_dungeness(self):
        from datetime import datetime, timezone
        import yaml
        self.source = Path(os.environ['CATALYST_DUNGENESS'])
        self.assertEqual(self.cli('--prepare-only', provider='openai-chatgpt', model='gpt-6-astra'), 0,
                         self.err.getvalue())
        metadata = self.metadata()
        runtime = Path(metadata['runtime'])
        spec = yaml_file(Path(metadata['spec_path']))
        module_spec = importlib.util.spec_from_file_location('public_local_compiler', runtime / 'src/dungeness/compiler.py')
        compiler = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(compiler)
        lock = yaml_file(runtime / 'verifiers/ecdsa-fail/benchmark-sh/evaluator.lock.yaml')
        def checkout(url, commit, destination):
            scaffold = yaml_file(runtime / 'scaffolds/ecdsa-point-add-sdk-v1/scaffold.yaml')
            for name in {*lock['include_paths'], *scaffold['workspace_paths'],
                         'src/point_add/mod.rs', 'src/point_add/old_solution.rs'}:
                path = destination / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('// fixture\n')
            (destination / 'src/bin/eval_circuit.rs').write_text(
                r'''fn main() {
    println!("\n-- correctness tests ({} shots) --", NUM_TESTS);
    let r = run_tests(&ops, &regs, total_qubits, num_bits, xof, NUM_TESTS);
    println!("  all {} shots OK", r.n_shots);
}
''')
        def reference(value):
            namespace, _, identity = value.split(':', 1)[1].rpartition('/')
            return namespace, identity
        tn, ti = reference(spec['task'])
        an, ai = reference(spec['agent'])
        rendered = None
        try:
            with patch.object(compiler, 'checkout', checkout), \
                    patch.object(compiler, 'apply_evaluator_patches', return_value=[]), \
                    patch.object(compiler, 'commit_timestamp', return_value=datetime(2026, 5, 29, tzinfo=timezone.utc)):
                rendered = compiler.build_task(ti, metadata['id'], task_namespace=tn, agent_id=ai,
                                               agent_namespace=an, namespace='projects/catalyst',
                                               checkpoint=spec['checkpoint'], run_spec=metadata['spec_path'],
                                               scaffold_start=spec['initialization']['mode'] == 'scaffold')
            compose = yaml.safe_load((rendered / 'environment/docker-compose.yaml').read_text())
            self.assertTrue(compose['services']['problem']['read_only'])
            self.assertTrue(compose['networks']['agent_internal']['internal'])
            self.assertNotIn('ports', compose['services']['problem'])
            self.assertEqual(compose['services']['main']['environment']['OPENAI_API_KEY'], 'testbed')
            self.assertNotIn('DUNGENESS_CHATGPT_AUTH_FILE', compose['services']['main']['environment'])
            self.assertEqual(read_json(rendered / 'environment/problem-service/task.json')['statement'],
                             problem_statement('ecdsa.fail'))
            candidate = rendered / 'environment/workspace/src/point_add'
            self.assertEqual([p.name for p in candidate.iterdir()], ['mod.rs'])
            self.assertEqual((candidate / 'mod.rs').read_bytes(),
                             (runtime / 'scaffolds/ecdsa-point-add-sdk-v1/candidate/mod.rs').read_bytes())
            for evaluator in (rendered / 'environment/workspace', rendered / 'tests/evaluator'):
                self.assertTrue((evaluator / 'src/point_add_sdk.rs').is_file())
                self.assertIn('pub mod point_add_sdk;', (evaluator / 'src/lib.rs').read_text())
                self.assertIn('&[1, 64, 512, NUM_TESTS]',
                              (evaluator / 'src/bin/eval_circuit.rs').read_text())
        finally:
            if rendered:
                shutil.rmtree(rendered.parent)
