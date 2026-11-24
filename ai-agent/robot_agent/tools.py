"""Tool definitions and execution for the agent.

A Tool is a Python function plus the JSON schema the model sees. The registry
validates the model's arguments before running anything and turns every
failure (unknown tool, bad arguments, exception) into an error result the
model can read, so one bad call never crashes the loop.
"""

import json
from dataclasses import dataclass
from typing import Any, Callable

_TYPES = {
    'string': str, 'integer': int, 'number': (int, float),
    'boolean': bool, 'object': dict, 'array': list,
}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema of the arguments object
    func: Callable[..., Any]

    def schema(self) -> dict[str, Any]:
        """Neutral tool definition handed to the model backend."""
        return {'name': self.name, 'description': self.description,
                'parameters': self.parameters}


@dataclass
class ToolResult:
    ok: bool
    content: str  # what the model reads (JSON text, truncated)


def validate_arguments(schema: dict[str, Any],
                       args: dict[str, Any]) -> list[str]:
    """Small JSON-schema subset: required, types, enum, extra keys."""
    errors = []
    if not isinstance(args, dict):
        return ['arguments must be a JSON object']
    props = schema.get('properties', {})
    for key in schema.get('required', []):
        if key not in args:
            errors.append(f'missing required argument "{key}"')
    for key, value in args.items():
        if key not in props:
            if schema.get('additionalProperties', True) is False:
                errors.append(f'unknown argument "{key}"')
            continue
        spec = props[key]
        expected = _TYPES.get(spec.get('type', ''))
        if expected and (not isinstance(value, expected)
                         or (spec.get('type') in ('integer', 'number')
                             and isinstance(value, bool))):
            errors.append(f'"{key}" must be {spec["type"]}')
        if 'enum' in spec and value not in spec['enum']:
            errors.append(f'"{key}" must be one of {spec["enum"]}')
    return errors


class ToolRegistry:
    def __init__(self, tools: list[Tool], max_result_chars: int = 2000):
        self.tools = {tool.name: tool for tool in tools}
        self.max_result_chars = max_result_chars

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self.tools.values()]

    def execute(self, name: str, args: dict[str, Any]) -> ToolResult:
        tool = self.tools.get(name)
        if tool is None:
            return self._error(f'unknown tool "{name}"; available: '
                               f'{sorted(self.tools)}')
        problems = validate_arguments(tool.parameters, args)
        if problems:
            return self._error('invalid arguments: ' + '; '.join(problems))
        try:
            value = tool.func(**args)
        except Exception as exc:  # report, never crash the loop
            return self._error(f'{exc.__class__.__name__}: {exc}')
        return ToolResult(True, self._render(value))

    def _render(self, value: Any) -> str:
        text = value if isinstance(value, str) else json.dumps(
            value, ensure_ascii=False, indent=1)
        if len(text) > self.max_result_chars:
            text = (text[:self.max_result_chars]
                    + f'\n...[truncated, {len(text)} chars total]')
        return text

    def _error(self, message: str) -> ToolResult:
        return ToolResult(False, json.dumps({'error': message},
                                            ensure_ascii=False))
