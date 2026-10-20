"""Strict offline API-format regressions for the stock Grok harness."""
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import unittest
import urllib.request

EXAMPLE = Path(__file__).resolve().parents[1] / 'examples' / 'stock-grok'
spec = importlib.util.spec_from_file_location('stock_grok_adapter', EXAMPLE / 'gateway_adapter.py')
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)

TITLE = {'type': 'function', 'name': 'session_title', 'description': 'Name this session',
         'parameters': {'type': 'object', 'properties': {'session_title': {'type': 'string'}},
                        'required': ['session_title'], 'additionalProperties': False}, 'strict': True}


class GrokAdapterTests(unittest.TestCase):
    def test_responses_and_chat_tools_have_one_chat_schema(self):
        function = {k: v for k, v in TITLE.items() if k != 'type'}
        for tool in (TITLE, {'type': 'function', 'function': function}):
            with self.subTest(tool=tool):
                request = adapter.sanitize_chat({'model': 'unassigned', 'tools': [tool],
                                                'tool_choice': {'type': 'function', 'name': 'session_title'}}, 'assigned')
                self.assertEqual(request['model'], 'assigned')
                self.assertEqual(request['tools'], [{'type': 'function', 'function': function}])
                self.assertEqual(request['tool_choice'], {'type': 'function', 'function': {'name': 'session_title'}})
                self.assertTrue(request['stream_options']['include_usage'])

    def test_tool_choice_modes(self):
        for value in ('auto', 'none', 'required', 'any'):
            expected = 'required' if value == 'any' else value
            self.assertEqual(adapter._sanitize_tool_choice(value), expected)
            self.assertEqual(adapter._sanitize_tool_choice({'type': value}), expected)
        named = {'type': 'function', 'function': {'name': 'session_title'}}
        self.assertEqual(adapter._sanitize_tool_choice(named), named)
        self.assertEqual(adapter._sanitize_tools([{'type': 'web_search'}, {'type': 'function', 'name': 7}]), [])

    def test_tool_result_round_trip(self):
        result = adapter.responses_to_chat({'input': [
            {'type': 'function_call', 'call_id': 'call_1', 'name': 'read_file', 'arguments': '{"path":"README"}'},
            {'type': 'function_call_output', 'call_id': 'call_1', 'output': 'file contents'},
        ]}, 'assigned')
        call, output = result['messages']
        self.assertEqual(call['tool_calls'][0]['function'], {'name': 'read_file', 'arguments': '{"path":"README"}'})
        self.assertEqual(output, {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'file contents'})

    def test_session_title_through_http_adapter_and_strict_upstream(self):
        requests = []
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                requests.append((self.path, payload, self.headers['Authorization']))
                valid = (all(isinstance(t.get('function'), dict) and t['function'].get('name')
                             for t in payload.get('tools', []))
                         and payload.get('tool_choice') == {'type': 'function', 'function': {'name': 'session_title'}})
                if not valid:
                    self.send_error(422, 'missing function wrapper'); return
                chunks = [
                    {'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 0, 'id': 'call_title',
                        'type': 'function', 'function': {'name': 'session_title', 'arguments': '{"session_title":'}}]}}]},
                    {'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 0,
                        'function': {'arguments': '"Research circuit"}'}}]}}]},
                    {'choices': [], 'usage': {'prompt_tokens': 100, 'completion_tokens': 10}},
                ]
                body = ''.join('data: ' + json.dumps(c) + '\n\n' for c in chunks).encode() + b'data: [DONE]\n\n'
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with adapter.compatible_gateway(f'http://127.0.0.1:{server.server_port}/model/grok-subscription/v1', 'grok-4.7') as base:
                payload = {'model': 'different-model', 'input': 'Name this research session', 'tools': [TITLE],
                           'tool_choice': {'type': 'function', 'name': 'session_title'}, 'max_output_tokens': 100}
                req = urllib.request.Request(base + '/responses', data=json.dumps(payload).encode(),
                                             headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    events = adapter._parse_sse(response.read().decode())
                completed = events[-1]['response']
                self.assertEqual(completed['output'][0]['name'], 'session_title')
                self.assertEqual(json.loads(completed['output'][0]['arguments']), {'session_title': 'Research circuit'})
                self.assertEqual(completed['output'][0]['call_id'], 'call_title')
                self.assertEqual(completed['usage']['input_tokens'], 100)
                self.assertEqual(completed['usage']['output_tokens'], 10)
            self.assertEqual(len(requests), 1)
            path, request, auth = requests[0]
            self.assertEqual(path, '/model/grok-subscription/v1/chat/completions')
            self.assertEqual(request['model'], 'grok-4.7')
            self.assertEqual(request['max_tokens'], 100)
            self.assertEqual(auth, 'Bearer testbed')
        finally:
            server.shutdown(); server.server_close(); thread.join()
