#!/usr/bin/env python3
"""Run the acceptance agent.

Examples:
  python3 run_agent.py --fake "Run every scenario and report which pass."
  python3 run_agent.py "Summarize the saved person_stop runs."
  python3 run_agent.py --model llama3.1:8b --max-turns 6 "Is the GPU usable?"
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from robot_agent.acceptance_tools import build_real_tools  # noqa: E402
from robot_agent.fake_tools import build_fake_tools  # noqa: E402
from robot_agent.llm import ModelError, OllamaChat  # noqa: E402
from robot_agent.loop import run_agent  # noqa: E402
from robot_agent.tools import ToolRegistry  # noqa: E402

SYSTEM_PROMPT = """You are a test engineer for a ROS 2 / Gazebo robot. \
A differential-drive vehicle uses a camera and YOLO to find a cup, approach \
it and stop; it must stop whenever a person is visible.

Use the tools to answer the user's request. Rules:
- Only state results that come from tool outputs; never invent numbers.
- Running a scenario takes about 1.5 minutes, so run only what the request \
needs, one at a time.
- If a tool returns an error, read it and fix the call or explain the problem.
- Finish with a short report: each scenario or run, PASS/FAIL, the key facts, \
and any failed check by name."""


def print_event(kind: str, data: dict) -> None:
    if kind == 'model_call':
        print(f"\n--- turn {data['turn']} ({data['model']})", flush=True)
    elif kind == 'thought':
        print(f"[model] {data['text']}")
    elif kind == 'tool_call':
        print(f"[tool call] {data['name']}("
              f"{json.dumps(data['arguments'], ensure_ascii=False)})",
              flush=True)
    elif kind == 'tool_result':
        text = data['content'].replace('\n', ' ')
        print(f"[tool result{'' if data['ok'] else ' ERROR'}] "
              f"{text[:300]}{'...' if len(text) > 300 else ''}")
    elif kind == 'final':
        print(f"\n=== final answer ===\n{data['text']}")
    elif kind == 'model_error':
        print(f"[model error] {data['error']}")
    elif kind == 'max_turns':
        print(f"[stopped] reached max turns ({data['turns']})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.
                                     RawDescriptionHelpFormatter)
    parser.add_argument('task', help='What the agent should do.')
    parser.add_argument('--model', default='qwen2.5:7b')
    parser.add_argument('--ollama-url', default=None,
                        help='Default: OLLAMA_HOST, localhost, WSL host IP.')
    parser.add_argument('--max-turns', type=int, default=8)
    parser.add_argument('--fake', action='store_true',
                        help='Use fake tools (no Gazebo).')
    args = parser.parse_args()

    tools = build_fake_tools() if args.fake else build_real_tools()
    try:
        model = OllamaChat(model=args.model, base_url=args.ollama_url)
    except ModelError as exc:
        print(f'Cannot reach Ollama: {exc}', file=sys.stderr)
        return 2
    print(f'model={model.name} url={model.base_url} '
          f"tools={'fake' if args.fake else 'real'}")
    result = run_agent(model, ToolRegistry(tools), SYSTEM_PROMPT, args.task,
                       max_turns=args.max_turns, on_event=print_event)
    print(f'\n[{result.stop_reason}] turns={result.turns} '
          f'tool_calls={result.tool_calls}')
    return 0 if result.stop_reason == 'final' else 1


if __name__ == '__main__':
    sys.exit(main())
