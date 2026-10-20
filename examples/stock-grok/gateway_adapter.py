"""Adapt stock Grok to the assigned Chat Completions gateway.

Grok 4.7 subscription routing accepts only chat/completions. The CLI still
sends its session-title side call to the Responses API, so that call is
translated and the stream is translated back. Every model request is forwarded
with the gateway placeholder; the gateway owns the real credential and meter.
"""
from contextlib import contextmanager
import http.client
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


CHAT_KEYS = {
    "model", "messages", "tools", "tool_choice", "functions", "function_call",
    "parallel_tool_calls", "stream", "stream_options", "max_tokens",
    "max_completion_tokens", "temperature", "top_p", "n", "stop", "logprobs",
    "top_logprobs", "logit_bias", "presence_penalty", "frequency_penalty",
    "seed", "user", "response_format", "reasoning_effort", "service_tier",
    "metadata", "store", "modalities",
}
MESSAGE_KEYS = {
    "role", "content", "name", "tool_calls", "tool_call_id", "function_call",
    "reasoning_content", "reasoning", "reasoning_details", "cache_control",
    "refusal",
}
ROLES = {"system", "developer", "user", "assistant", "tool", "function"}
TEXT_BLOCKS = {"text", "input_text", "output_text"}


def _model_catalog(model_id):
    return {
        "object": "list",
        "data": [{
            "id": model_id,
            "object": "model",
            "model": model_id,
            "owned_by": "xai",
            "name": "Grok 4.7",
            "api_backend": "chat_completions",
            "auth_scheme": "bearer",
            "context_window": 256000,
            "supported_in_api": True,
            "supports_reasoning_effort": True,
            "reasoning_effort": "high",
        }],
    }


def _copy(source, keys):
    if not isinstance(source, dict):
        return {}
    return {key: source[key] for key in keys if key in source}


def _sanitize_content(content):
    if isinstance(content, str) or content is None:
        return content
    if not isinstance(content, list):
        return ""
    blocks = []
    for block in content:
        if isinstance(block, str):
            blocks.append({"type": "text", "text": block})
            continue
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind in TEXT_BLOCKS and isinstance(block.get("text"), str):
            blocks.append({"type": kind, "text": block["text"]})
        elif kind in {"thinking", "redacted_thinking", "reasoning"}:
            kept = _copy(block, {"type", "thinking", "signature", "data", "text"})
            if "type" in kept:
                blocks.append(kept)
        elif kind == "tool_use":
            kept = _copy(block, {"type", "id", "name", "input"})
            if kept.get("caller", {"type": "direct"}) == {"type": "direct"}:
                blocks.append(kept)
        elif kind == "tool_result":
            kept = _copy(block, {"type", "tool_use_id", "is_error"})
            if "content" in block:
                kept["content"] = _sanitize_content(block["content"])
            blocks.append(kept)
        elif kind == "refusal" and "refusal" in block:
            blocks.append({"type": "refusal", "refusal": block["refusal"]})
    return blocks


def _sanitize_tool_calls(calls):
    cleaned = []
    if not isinstance(calls, list):
        return cleaned
    for call in calls:
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        arguments = function.get("arguments", call.get("arguments", ""))
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments)
        item = {
            "id": call.get("id") or call.get("call_id") or "call",
            "type": "function",
            "function": {"name": function.get("name") or call.get("name") or "", "arguments": arguments},
        }
        if "index" in call:
            item["index"] = call["index"]
        cleaned.append(item)
    return cleaned


def _sanitize_message(message):
    if not isinstance(message, dict) or message.get("role") not in ROLES:
        return None
    cleaned = {"role": message["role"]}
    if "content" in message:
        cleaned["content"] = _sanitize_content(message.get("content"))
    for key in ("name", "tool_call_id", "reasoning_content", "reasoning", "reasoning_details", "refusal"):
        if key in message:
            cleaned[key] = message[key]
    calls = _sanitize_tool_calls(message.get("tool_calls"))
    if calls:
        cleaned["tool_calls"] = calls
    function_call = message.get("function_call")
    if isinstance(function_call, dict):
        arguments = function_call.get("arguments", "")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments)
        cleaned["function_call"] = {"name": function_call.get("name") or "", "arguments": arguments}
    return {key: value for key, value in cleaned.items() if key in MESSAGE_KEYS}


def _sanitize_tools(tools):
    """The Grok subscription proxy accepts only nested function tools."""
    cleaned = []
    if not isinstance(tools, list):
        return cleaned
    for tool in tools:
        if not isinstance(tool, dict) or tool.get("type", "function") != "function":
            continue
        nested = tool.get("function") if isinstance(tool.get("function"), dict) else {}
        function = _copy(nested, {"name", "description", "parameters", "strict"})
        if "name" not in function and isinstance(tool.get("name"), str):
            function["name"] = tool["name"]
        for key in ("description", "parameters", "strict"):
            if key not in function and key in tool:
                function[key] = tool[key]
        if isinstance(function.get("name"), str) and function["name"]:
            cleaned.append({"type": "function", "function": function})
    return cleaned


def _sanitize_tool_choice(choice):
    if choice is None or (isinstance(choice, str) and choice in {"none", "auto", "required", "any"}):
        return "required" if choice == "any" else choice
    if not isinstance(choice, dict):
        return "auto"
    kind = choice.get("type")
    if kind == "function":
        name = choice.get("name")
        function = choice.get("function") if isinstance(choice.get("function"), dict) else {}
        name = name or function.get("name")
        if isinstance(name, str) and name:
            return {"type": "function", "function": {"name": name}}
    if kind in {"none", "auto", "required", "any"}:
        return "required" if kind == "any" else kind
    return "auto"


def sanitize_chat(payload, gateway_model):
    """Keep a closed Chat Completions subset and pin the declared model."""
    if not isinstance(payload, dict):
        raise ValueError("Chat request must be an object.")
    messages = [_sanitize_message(item) for item in payload.get("messages") or []]
    cleaned = {
        "model": gateway_model,
        "messages": [item for item in messages if item],
        "stream": payload.get("stream") is not False,
    }
    for key in CHAT_KEYS - {"model", "messages", "stream", "tools", "tool_choice", "stream_options",
                            "functions", "function_call", "response_format", "reasoning_effort",
                            "service_tier", "modalities"}:
        if key in payload:
            cleaned[key] = payload[key]
    if payload.get("reasoning_effort") in {"low", "medium", "high", "xhigh", "max"}:
        cleaned["reasoning_effort"] = payload["reasoning_effort"]
    if payload.get("service_tier") in {"auto", "default"}:
        cleaned["service_tier"] = payload["service_tier"]
    if payload.get("modalities") == ["text"]:
        cleaned["modalities"] = ["text"]
    tools = _sanitize_tools(payload.get("tools"))
    if tools:
        cleaned["tools"] = tools
    if payload.get("tool_choice") is not None:
        cleaned["tool_choice"] = _sanitize_tool_choice(payload["tool_choice"])
    if cleaned["stream"]:
        options = payload.get("stream_options") if isinstance(payload.get("stream_options"), dict) else {}
        stream_options = {"include_usage": True}
        if "include_obfuscation" in options:
            stream_options["include_obfuscation"] = bool(options["include_obfuscation"])
        cleaned["stream_options"] = stream_options
    response_format = payload.get("response_format")
    if isinstance(response_format, dict) and set(response_format) <= {"type", "json_schema"} and response_format.get("type") in {"text", "json_object", "json_schema"}:
        cleaned["response_format"] = response_format
    return cleaned


def _input_messages(payload):
    messages = []
    instructions = payload.get("instructions")
    if isinstance(instructions, str) and instructions:
        messages.append({"role": "system", "content": instructions})
    raw = payload.get("input")
    items = [{"type": "message", "role": "user", "content": raw}] if isinstance(raw, str) else raw
    if not isinstance(items, list):
        return messages
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("type", "message")
        if kind == "message":
            role = item.get("role") or "user"
            if role == "developer":
                role = "system"
            messages.append({"role": role if role in ROLES else "user", "content": item.get("content", "")})
        elif kind == "function_call":
            arguments = item.get("arguments", "")
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments)
            messages.append({"role": "assistant", "content": None, "tool_calls": [{
                "id": item.get("call_id") or item.get("id") or "call",
                "type": "function",
                "function": {"name": item.get("name") or "", "arguments": arguments},
            }]})
        elif kind == "function_call_output":
            output = item.get("output", "")
            if not isinstance(output, str):
                output = json.dumps(output)
            messages.append({"role": "tool", "tool_call_id": item.get("call_id") or "", "content": output})
    return messages


def responses_to_chat(payload, gateway_model):
    """Turn one Responses request into a policy-safe Chat Completions request."""
    chat = {
        "model": gateway_model,
        "messages": _input_messages(payload),
        "stream": True,
    }
    if "temperature" in payload:
        chat["temperature"] = payload["temperature"]
    if isinstance(payload.get("max_output_tokens"), int):
        chat["max_tokens"] = payload["max_output_tokens"]
    if payload.get("tools"):
        chat["tools"] = payload["tools"]
    if payload.get("tool_choice") is not None:
        chat["tool_choice"] = payload["tool_choice"]
    reasoning = payload.get("reasoning")
    if isinstance(reasoning, dict) and reasoning.get("effort") in {"low", "medium", "high", "xhigh", "max"}:
        chat["reasoning_effort"] = reasoning["effort"]
    return sanitize_chat(chat, gateway_model)


def _parse_sse(body):
    events = []
    for block in body.split("\n\n"):
        data = []
        for line in block.splitlines():
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
        if not data:
            continue
        raw = "\n".join(data).strip()
        if raw == "[DONE]":
            events.append(None)
        else:
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return events


def _usage_from_chat(usage):
    usage = usage if isinstance(usage, dict) else {}
    prompt = usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
    completion = usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
    details = usage.get("prompt_tokens_details") or usage.get("input_tokens_details") or {}
    output_details = usage.get("completion_tokens_details") or usage.get("output_tokens_details") or {}
    cached = details.get("cached_tokens", 0) if isinstance(details, dict) else 0
    reasoning = output_details.get("reasoning_tokens", 0) if isinstance(output_details, dict) else 0
    return {
        "input_tokens": prompt,
        "input_tokens_details": {"cached_tokens": cached or 0},
        "output_tokens": completion,
        "output_tokens_details": {"reasoning_tokens": reasoning or 0},
        "total_tokens": usage.get("total_tokens", prompt + completion) or 0,
    }


def _collect_chat(events):
    text = []
    calls = {}
    usage = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        if isinstance(event.get("usage"), dict):
            usage = event["usage"]
        choices = event.get("choices")
        if not isinstance(choices, list):
            message = event.get("message") if isinstance(event.get("message"), dict) else None
            if message is None and isinstance(event.get("choices"), list):
                message = None
            if isinstance(event.get("choices"), list) and event["choices"] and isinstance(event["choices"][0], dict):
                message = event["choices"][0].get("message")
            if isinstance(message, dict):
                if isinstance(message.get("content"), str):
                    text.append(message["content"])
                for call in _sanitize_tool_calls(message.get("tool_calls")):
                    calls[call["id"]] = call
            continue
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
            message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
            content = delta.get("content", message.get("content"))
            if isinstance(content, str):
                text.append(content)
            for call in delta.get("tool_calls") or message.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                index = call.get("index", 0)
                slot = calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                if call.get("id"):
                    slot["id"] = call["id"]
                function = call.get("function") if isinstance(call.get("function"), dict) else {}
                if function.get("name"):
                    slot["name"] = function["name"]
                if call.get("name"):
                    slot["name"] = call["name"]
                arguments = function.get("arguments", call.get("arguments"))
                if isinstance(arguments, str):
                    slot["arguments"] += arguments
                elif arguments is not None:
                    slot["arguments"] += json.dumps(arguments)
    ordered = [calls[key] for key in sorted(calls, key=lambda item: (isinstance(item, str), item))]
    return "".join(text), ordered, _usage_from_chat(usage)


def chat_to_responses_sse(body, model):
    """Buffer a small Chat Completions stream into Responses events Grok accepts."""
    parsed = json.loads(body) if body.lstrip().startswith(b"{") else None
    events = [parsed] if isinstance(parsed, dict) else _parse_sse(body.decode("utf-8", "replace"))
    text, calls, usage = _collect_chat(events)
    output = []
    for index, call in enumerate(calls):
        output.append({
            "type": "function_call",
            "id": "fc_%d" % index,
            "call_id": call["id"] or "call_%d" % index,
            "name": call["name"],
            "status": "completed",
            "arguments": call["arguments"] or "{}",
        })
    if text or not output:
        output.append({
            "id": "msg_0",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        })
    created = int(time.time())
    completed = {
        "id": "resp_gateway",
        "object": "response",
        "created_at": created,
        "model": model,
        "status": "completed",
        "output": output,
        "usage": usage,
    }
    inflight = {**completed, "status": "in_progress", "output": []}
    stream = [("response.created", {"response": inflight})]
    for index, item in enumerate(output):
        stream.append(("response.output_item.done", {"output_index": index, "item": item}))
    stream.append(("response.completed", {"response": completed}))
    encoded = []
    for sequence, (name, extra) in enumerate(stream):
        event = {"type": name, "sequence_number": sequence, **extra}
        encoded.append("event: %s\ndata: %s\n\n" % (name, json.dumps(event)))
    return "".join(encoded).encode()


def _read_bounded(response, limit):
    chunks, total = [], 0
    while True:
        chunk = response.read1(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ValueError("Gateway response is too large.")
        chunks.append(chunk)
    return b"".join(chunks)


@contextmanager
def compatible_gateway(base_url, gateway_model, cli_model="grok-4.7"):
    target = urlsplit(base_url)
    if target.scheme != "http" or target.username or target.password or target.query or target.fragment:
        raise ValueError("Expected the assigned internal HTTP gateway.")
    upstream = target.path.rstrip("/") + "/chat/completions"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, status, payload):
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path.split("?", 1)[0].rstrip("/") in {"/v1/models", "/models"}:
                self._json(200, _model_catalog(cli_model))
                return
            self.send_error(404)

        def _forward(self, payload):
            connection = http.client.HTTPConnection(target.hostname, target.port, timeout=900)
            try:
                connection.request(
                    "POST", upstream,
                    body=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json", "Accept": "text/event-stream",
                             "Authorization": "Bearer testbed"},
                )
                return connection, connection.getresponse()
            except Exception:
                connection.close()
                raise

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            responses = path in {"/v1/responses", "/v1/responses/compact"}
            if path != "/v1/chat/completions" and not responses:
                self.send_error(404)
                return
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 16 * 1024 * 1024:
                self.send_error(413)
                return
            try:
                payload = json.loads(self.rfile.read(size))
                chat = responses_to_chat(payload, gateway_model) if responses else sanitize_chat(payload, gateway_model)
            except (ValueError, json.JSONDecodeError):
                self.send_error(400)
                return
            connection = None
            try:
                connection, response = self._forward(chat)
                if responses and response.status == 200:
                    raw = chat_to_responses_sse(_read_bounded(response, 32 * 1024 * 1024), gateway_model)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Content-Length", str(len(raw)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(raw)
                    return
                self.send_response(response.status)
                self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                while chunk := response.read1(65536):
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except Exception:
                self.send_error(502)
            finally:
                if connection is not None:
                    connection.close()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
