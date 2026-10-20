"""Run the actual Grok CLI against a strict local mock inside its offline image.

Mount examples/stock-grok at /opt/harness and this file at /tmp/smoke.py, then
run python3 /tmp/smoke.py in catalyst-stock-grok:1.0.62 with --network none.
No real credentials or model calls are used.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import traceback


requests = []
errors = []


class Upstream(BaseHTTPRequestHandler):
    def log_message(self, *args): pass

    def do_POST(self):
        try:
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert self.path == '/model/grok-subscription/v1/chat/completions'
            assert self.headers['Authorization'] == 'Bearer testbed'
            assert payload['model'] == 'grok-4.7'
            tools = payload.get('tools', [])
            assert all(t['type'] == 'function' and t['function']['name'] for t in tools)
            choice = payload.get('tool_choice')
            if isinstance(choice, dict):
                assert choice['type'] == 'function' and choice['function']['name']
            requests.append(payload)
            title = any(t['function']['name'] == 'session_title' for t in tools)
            finished = not tools or any(m['role'] == 'tool' for m in payload['messages'])
            if title:
                name, arguments = 'session_title', {'session_title': 'Offline gateway smoke test'}
            elif not finished:
                assert any(t['function']['name'] == 'run_terminal_command' for t in tools)
                name, arguments = 'run_terminal_command', {
                    'command': "printf 'offline tool succeeded\\n' > smoke-marker.txt",
                    'description': 'Write the offline test marker', 'block_until_ms': 1000,
                }
            if title or not finished:
                delta = {'role': 'assistant', 'tool_calls': [{'index': 0, 'id': 'call_smoke',
                    'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}]}
                finish = 'tool_calls'
            else:
                delta = {'role': 'assistant', 'content': 'Offline test completed.'}; finish = 'stop'
            chunks = [
                {'id': 'chatcmpl-smoke', 'object': 'chat.completion.chunk', 'model': 'grok-4.7',
                 'choices': [{'index': 0, 'delta': delta, 'finish_reason': None}]},
                {'id': 'chatcmpl-smoke', 'object': 'chat.completion.chunk', 'model': 'grok-4.7',
                 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]},
                {'choices': [], 'usage': {'prompt_tokens': 100, 'completion_tokens': 10, 'total_tokens': 110}},
            ]
            chunks = [{'id': 'chatcmpl-smoke', 'object': 'chat.completion.chunk',
                       'model': 'grok-4.7', 'created': 1792462902, **chunk} for chunk in chunks]
            body = ''.join('data: ' + json.dumps(c) + '\n\n' for c in chunks).encode() + b'data: [DONE]\n\n'
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        except Exception as error:
            errors.append(traceback.format_exc()); self.send_error(422, 'Strict mock rejected request')


server = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
try:
    with tempfile.TemporaryDirectory() as temp:
        workspace = Path(temp)
        task = workspace / 'task.json'
        task.write_text(json.dumps({
            'instruction': 'Write smoke-marker.txt with the text offline tool succeeded, then finish.',
            'workspace': str(workspace), 'gateway_auth': 'placeholder', 'model': 'grok-4.7',
            'gateway': f'http://127.0.0.1:{server.server_port}/model/grok-subscription/v1',
        }))
        version = subprocess.check_output(['grok', '--version'], text=True)
        assert '1.0.62' in version, version
        run = subprocess.run(['python3', '/opt/harness/agent.py'],
            env={**os.environ, 'CATALYST_TASK': str(task)}, text=True, capture_output=True, timeout=90)
        assert run.returncode == 0 and '"exit_code": 0' in run.stdout, (run.stdout, run.stderr)
        assert not errors, errors
        assert (workspace / 'smoke-marker.txt').read_text() == 'offline tool succeeded\n'
        assert any(t['function']['name'] == 'session_title' for r in requests for t in r.get('tools', []))
        assert any(m['role'] == 'tool' for r in requests for m in r['messages'])
        print(f'PASS: Grok CLI 1.0.62, title request, tool execution and tool result; {len(requests)} mock calls, no inference.')
finally:
    server.shutdown(); server.server_close(); thread.join()
