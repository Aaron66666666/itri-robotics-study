"""Provider-neutral message types used by the agent loop.

The loop only ever sees these classes. Each model backend (llm.py) converts
them to and from its own wire format, so switching from a local Ollama model
to another provider later only means adding a backend.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """One tool call requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    """One conversation entry.

    role: 'system' | 'user' | 'assistant' | 'tool'
    tool_calls: set on assistant messages that request tools.
    tool_call_id / name: set on 'tool' messages (which call they answer).
    """

    role: str
    content: str = ''
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
