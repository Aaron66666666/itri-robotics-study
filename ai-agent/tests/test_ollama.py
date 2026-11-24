"""Ollama backend tests against a local fake /api/chat server."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from robot_agent.fake_tools import build_fake_tools
from robot_agent.llm import ModelError, OllamaChat, find_ollama
from robot_agent.loop import run_agent
from robot_agent.messages import Message, ToolCall
from robot_agent.tools import ToolRegistry


class FakeOllama:
    """Serves /api/version and replays scripted /api/chat replies."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, obj, code=200):
                body = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._send({'version': 'fake'})

            def do_POST(self):
                length = int(self.headers['Content-Length'])
                outer.requests.append(json.loads(self.rfile.read(length)))
                reply = outer.replies.pop(0)
                self._send(reply, 500 if 'error' in reply else 200)

        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        threading.Thread(target=self.server.serve_forever,
                         daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def fake_server():
    servers = []

    def make(replies):
        server = FakeOllama(replies)
        servers.append(server)
        return server
    yield make
    for server in servers:
        server.close()


def tool_reply(name, args):
    return {'message': {'role': 'assistant', 'content': '',
                        'tool_calls': [{'function': {'name': name,
                                                     'arguments': args}}]},
            'done': True}


def text_reply(text):
    return {'message': {'role': 'assistant', 'content': text}, 'done': True}


def test_request_format_and_tool_call_parsing(fake_server):
    server = fake_server([tool_reply('run_scenario',
                                     {'scenario': 'approach'})])
    model = OllamaChat(model='qwen2.5:7b', base_url=server.url)
    tools = ToolRegistry(build_fake_tools()).schemas()
    reply = model.chat([Message('system', 's'), Message('user', 'u')], tools)
    body = server.requests[0]
    assert body['model'] == 'qwen2.5:7b' and body['stream'] is False
    assert body['tools'][0]['type'] == 'function'
    assert body['tools'][0]['function']['name'] == 'list_scenarios'
    assert body['options']['temperature'] == 0.0
    assert reply.tool_calls[0].name == 'run_scenario'
    assert reply.tool_calls[0].arguments == {'scenario': 'approach'}


def test_tool_messages_sent_back_with_tool_name():
    wire = OllamaChat.to_wire([
        Message('assistant', tool_calls=[ToolCall('c1', 'get_gpu_status',
                                                  {})]),
        Message('tool', '{"ok": 1}', tool_call_id='c1',
                name='get_gpu_status')])
    assert wire[0]['tool_calls'][0]['function']['name'] == 'get_gpu_status'
    assert wire[1] == {'role': 'tool', 'content': '{"ok": 1}',
                       'tool_name': 'get_gpu_status'}


@pytest.mark.parametrize('content', [
    '{"name": "get_gpu_status", "arguments": {}}',
    '```json\n{"name": "get_gpu_status", "arguments": {}}\n```',
    'Calling: {"name": "get_gpu_status", "parameters": {}}',
])
def test_tool_call_written_as_text_is_recovered(content):
    msg = OllamaChat.from_wire({'message': {'content': content}},
                               {'get_gpu_status'}, lambda: 'id1')
    assert msg.tool_calls[0].name == 'get_gpu_status'
    assert msg.content == ''


def test_plain_text_mentioning_unknown_json_stays_text():
    text = 'Result: {"name": "not_a_tool", "arguments": {}}'
    msg = OllamaChat.from_wire({'message': {'content': text}},
                               {'get_gpu_status'}, lambda: 'id1')
    assert msg.tool_calls == [] and msg.content == text


def test_string_arguments_are_parsed():
    data = {'message': {'tool_calls': [{'function': {
        'name': 'run_scenario', 'arguments': '{"scenario": "approach"}'}}]}}
    msg = OllamaChat.from_wire(data, set(), lambda: 'id1')
    assert msg.tool_calls[0].arguments == {'scenario': 'approach'}


def test_http_error_becomes_model_error(fake_server):
    server = fake_server([{'error': 'model "x" not found'}])
    model = OllamaChat(model='x', base_url=server.url)
    with pytest.raises(ModelError, match='not found'):
        model.chat([Message('user', 'hi')], [])


def test_find_ollama_uses_env_first(fake_server, monkeypatch):
    server = fake_server([])
    monkeypatch.setenv('OLLAMA_HOST', server.url)
    assert find_ollama() == server.url


def test_full_agent_run_through_ollama_backend(fake_server):
    server = fake_server([
        tool_reply('run_scenario', {'scenario': 'person_stop'}),
        text_reply('person_stop: PASS, stopped in 94 ms.'),
    ])
    model = OllamaChat(base_url=server.url)
    result = run_agent(model, ToolRegistry(build_fake_tools()), 'sys',
                       'check person stop')
    assert result.stop_reason == 'final'
    assert '94 ms' in result.final_text
    second = server.requests[1]['messages']
    assert second[-1]['role'] == 'tool'
    assert second[-1]['tool_name'] == 'run_scenario'
    assert json.loads(second[-1]['content'])['verdict'] == 'PASS'
