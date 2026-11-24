"""The agent loop: model -> tool calls -> tool results -> model ...

Stops when the model answers without tool calls, or after max_turns model
calls. Every step is reported through on_event so a CLI (or a test) can show
or record what happened.
"""

import json
from dataclasses import dataclass, field
from typing import Callable, Optional

from .llm import ChatModel, ModelError
from .messages import Message
from .tools import ToolRegistry, ToolResult

REPEAT_LIMIT = 2  # identical calls allowed before the loop refuses

# A policy sees (tool name, arguments) and returns None to allow the call or
# an error message to refuse it. Rules that must hold (e.g. "never start a
# simulation the user did not ask for") are enforced here in code, because a
# small model does not follow every prompt instruction.
Policy = Callable[[str, dict], Optional[str]]


@dataclass
class AgentResult:
    stop_reason: str  # 'final' | 'max_turns' | 'model_error'
    final_text: str
    turns: int
    tool_calls: int
    transcript: list[Message] = field(default_factory=list)


def _key(name: str, args: dict) -> str:
    return name + json.dumps(args, sort_keys=True, ensure_ascii=False)


def run_agent(model: ChatModel, registry: ToolRegistry, system: str,
              task: str, max_turns: int = 8,
              on_event: Callable[[str, dict], None] | None = None,
              policy: Policy | None = None) -> AgentResult:
    emit = on_event or (lambda kind, data: None)
    messages = [Message('system', system), Message('user', task)]
    seen: dict[str, int] = {}
    tool_calls = 0
    for turn in range(1, max_turns + 1):
        emit('model_call', {'turn': turn, 'model': model.name})
        try:
            reply = model.chat(messages, registry.schemas())
        except ModelError as exc:
            emit('model_error', {'turn': turn, 'error': str(exc)})
            return AgentResult('model_error', str(exc), turn, tool_calls,
                               messages)
        messages.append(reply)
        if not reply.tool_calls:
            emit('final', {'turn': turn, 'text': reply.content})
            return AgentResult('final', reply.content, turn, tool_calls,
                               messages)
        if reply.content:
            emit('thought', {'turn': turn, 'text': reply.content})
        for call in reply.tool_calls:
            tool_calls += 1
            key = _key(call.name, call.arguments)
            seen[key] = seen.get(key, 0) + 1
            emit('tool_call', {'turn': turn, 'name': call.name,
                               'arguments': call.arguments})
            refusal = policy(call.name, call.arguments) if policy else None
            if refusal:
                emit('policy_refused', {'turn': turn, 'name': call.name,
                                        'reason': refusal})
                result = ToolResult(False, json.dumps({'error': refusal},
                                                      ensure_ascii=False))
            elif seen[key] > REPEAT_LIMIT:
                result = ToolResult(False, json.dumps({
                    'error': 'same call already made '
                             f'{REPEAT_LIMIT} times; use the earlier '
                             'result or try something else'}))
            else:
                result = registry.execute(call.name, call.arguments)
            emit('tool_result', {'turn': turn, 'name': call.name,
                                 'ok': result.ok, 'content': result.content})
            messages.append(Message('tool', result.content,
                                    tool_call_id=call.id, name=call.name))
    emit('max_turns', {'turns': max_turns})
    return AgentResult('max_turns',
                       f'Stopped after {max_turns} model turns without a '
                       'final answer.', max_turns, tool_calls, messages)
