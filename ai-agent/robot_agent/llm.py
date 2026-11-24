"""Model backends. The agent loop depends only on ChatModel.chat().

Backends here:
  OllamaChat    - local model served by Ollama (/api/chat, tool calling).
  ScriptedModel - deterministic fake model for tests (no network).

To use another provider later (e.g. a hosted API), add a class with the same
chat(messages, tools) -> Message method that converts to/from its wire
format. Nothing in loop.py or the tools needs to change.
"""

import json
import os
import subprocess
import urllib.error
import urllib.request
from typing import Any, Callable, Iterable

from .messages import Message, ToolCall


class ModelError(RuntimeError):
    """The model backend failed (unreachable, bad response, ...)."""


class ChatModel:
    """Interface every backend implements."""

    name = 'base'

    def chat(self, messages: list[Message],
             tools: list[dict[str, Any]]) -> Message:
        """Return the next assistant message (text and/or tool calls).

        tools: JSON-schema tool definitions in the neutral form
        {"name", "description", "parameters"} (see tools.py).
        """
        raise NotImplementedError

    def chat_json(self, messages: list[Message],
                  schema: dict[str, Any]) -> dict[str, Any]:
        """Return a JSON object that follows `schema` (structured output)."""
        raise NotImplementedError


# --------------------------------------------------------------- Ollama
def _windows_host_ip() -> str | None:
    """Default-gateway IP = the Windows host when WSL uses NAT networking."""
    try:
        out = subprocess.run(['ip', 'route'], capture_output=True, text=True,
                             timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        parts = line.split()
        if parts[:2] == ['default', 'via'] and len(parts) > 2:
            return parts[2]
    return None


def candidate_ollama_urls() -> list[str]:
    """OLLAMA_HOST first, then localhost (mirrored WSL), then the NAT host."""
    urls = []
    env = os.environ.get('OLLAMA_HOST', '').strip()
    if env:
        urls.append(env if env.startswith('http') else f'http://{env}')
    urls.append('http://localhost:11434')
    host_ip = _windows_host_ip()
    if host_ip:
        urls.append(f'http://{host_ip}:11434')
    seen, unique = set(), []
    for url in urls:
        url = url.rstrip('/')
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def _http_json(url: str, payload: dict | None, timeout: float) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url, data=data, headers={'Content-Type': 'application/json'},
        method='GET' if payload is None else 'POST')
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


def find_ollama(timeout: float = 2.0) -> str:
    """Return the first reachable Ollama base URL, or raise ModelError."""
    tried = []
    for url in candidate_ollama_urls():
        try:
            _http_json(f'{url}/api/version', None, timeout)
            return url
        except (urllib.error.URLError, OSError, ValueError) as exc:
            tried.append(f'{url} ({exc.__class__.__name__})')
    raise ModelError('Ollama not reachable; tried: ' + ', '.join(tried))


class OllamaChat(ChatModel):
    """Ollama /api/chat with native tool calling (non-streaming)."""

    def __init__(self, model: str = 'qwen2.5:7b', base_url: str | None = None,
                 temperature: float = 0.0, timeout: float = 300.0,
                 num_ctx: int = 8192):
        self.model = model
        self.name = f'ollama:{model}'
        self.base_url = (base_url or find_ollama()).rstrip('/')
        self.temperature = temperature
        self.timeout = timeout
        self.num_ctx = num_ctx

    # neutral -> Ollama
    @staticmethod
    def to_wire(messages: Iterable[Message]) -> list[dict[str, Any]]:
        wire = []
        for msg in messages:
            item: dict[str, Any] = {'role': msg.role, 'content': msg.content}
            if msg.tool_calls:
                item['tool_calls'] = [
                    {'function': {'name': c.name, 'arguments': c.arguments}}
                    for c in msg.tool_calls]
            if msg.role == 'tool' and msg.name:
                item['tool_name'] = msg.name
            wire.append(item)
        return wire

    @staticmethod
    def tools_to_wire(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{'type': 'function', 'function': tool} for tool in tools]

    # Ollama -> neutral
    @staticmethod
    def from_wire(data: dict[str, Any], tool_names: set[str],
                  next_id: Callable[[], str]) -> Message:
        raw = data.get('message') or {}
        content = raw.get('content') or ''
        calls = []
        for call in raw.get('tool_calls') or []:
            fn = call.get('function') or {}
            args = fn.get('arguments') or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {'_unparsed': args}
            calls.append(ToolCall(id=call.get('id') or next_id(),
                                  name=fn.get('name', ''), arguments=args))
        if not calls:
            # Small local models sometimes write the call as JSON text.
            text_call = _tool_call_from_text(content, tool_names)
            if text_call:
                calls.append(ToolCall(id=next_id(), name=text_call[0],
                                      arguments=text_call[1]))
                content = ''
        return Message(role='assistant', content=content, tool_calls=calls)

    def chat(self, messages: list[Message],
             tools: list[dict[str, Any]]) -> Message:
        payload = {
            'model': self.model,
            'messages': self.to_wire(messages),
            'tools': self.tools_to_wire(tools),
            'stream': False,
            'options': {'temperature': self.temperature,
                        'num_ctx': self.num_ctx},
        }
        try:
            data = _http_json(f'{self.base_url}/api/chat', payload,
                              self.timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors='replace')[:300]
            raise ModelError(f'Ollama HTTP {exc.code}: {body}') from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ModelError(f'Ollama request failed: {exc}') from exc
        if 'error' in data:
            raise ModelError(f"Ollama error: {data['error']}")
        counter = sum(len(m.tool_calls) for m in messages)

        def next_id():
            nonlocal counter
            counter += 1
            return f'call_{counter}'
        return self.from_wire(data, {t['name'] for t in tools}, next_id)

    def chat_json(self, messages: list[Message],
                  schema: dict[str, Any]) -> dict[str, Any]:
        """Ollama structured outputs: 'format' carries the JSON schema."""
        payload = {
            'model': self.model, 'messages': self.to_wire(messages),
            'format': schema, 'stream': False,
            'options': {'temperature': self.temperature,
                        'num_ctx': self.num_ctx},
        }
        try:
            data = _http_json(f'{self.base_url}/api/chat', payload,
                              self.timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors='replace')[:300]
            raise ModelError(f'Ollama HTTP {exc.code}: {body}') from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ModelError(f'Ollama request failed: {exc}') from exc
        text = (data.get('message') or {}).get('content') or ''
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ModelError(f'model did not return JSON: {text[:200]}') \
                from exc
        if not isinstance(value, dict):
            raise ModelError('model returned JSON that is not an object')
        return value


def _tool_call_from_text(text: str,
                         tool_names: set[str]) -> tuple[str, dict] | None:
    """Parse '{"name": ..., "arguments": {...}}' written as plain text."""
    stripped = text.strip()
    if stripped.startswith('```'):
        stripped = stripped.strip('`')
        stripped = stripped.split('\n', 1)[-1] if '\n' in stripped else ''
    start, end = stripped.find('{'), stripped.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(stripped[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    name = obj.get('name')
    args = obj.get('arguments', obj.get('parameters', {}))
    if name in tool_names and isinstance(args, dict):
        return name, args
    return None


# ------------------------------------------------------------ test model
class ScriptedModel(ChatModel):
    """Replays a fixed list of assistant replies; records what it was sent.

    Each step is either a Message or a function(messages) -> Message, so a
    test can make the reply depend on the tool results seen so far.
    """

    name = 'scripted'

    def __init__(self, steps: list):
        self.steps = list(steps)
        self.calls: list[list[Message]] = []

    def chat(self, messages, tools):
        self.calls.append(list(messages))
        if not self.steps:
            raise ModelError('ScriptedModel has no more replies')
        step = self.steps.pop(0)
        return step(messages) if callable(step) else step

    def chat_json(self, messages, schema):
        """Steps for JSON calls are dicts (or functions returning dicts)."""
        self.calls.append(list(messages))
        if not self.steps:
            raise ModelError('ScriptedModel has no more replies')
        step = self.steps.pop(0)
        return step(messages) if callable(step) else step
