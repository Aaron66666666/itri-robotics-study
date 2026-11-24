#!/usr/bin/env python3
"""Run the acceptance agent.

Examples:
  python3 run_agent.py --fake "Run every scenario and report which pass."
  python3 run_agent.py "Summarize the saved person_stop runs."
  python3 run_agent.py --model llama3.1:8b --max-turns 6 "Is the GPU usable?"
  python3 run_agent.py --multi "Run person_stop on the GPU and report."
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from robot_agent.acceptance_tools import (  # noqa: E402
    build_real_tools, scenario_policy)
from robot_agent.fake_tools import build_fake_tools  # noqa: E402
from robot_agent.llm import ModelError, OllamaChat  # noqa: E402
from robot_agent.loop import run_agent  # noqa: E402
from robot_agent.multi_agent import run_multi_agent  # noqa: E402
from robot_agent.prompts import SYSTEM_PROMPT  # noqa: E402
from robot_agent.tools import ToolRegistry  # noqa: E402


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
    elif kind == 'policy_refused':
        print(f"[policy] refused {data['name']}: {data['reason']}")
    elif kind == 'model_error':
        print(f"[model error] {data['error']}")
    elif kind == 'max_turns':
        print(f"[stopped] reached max turns ({data['turns']})")


def print_multi_event(kind: str, data: dict) -> None:
    if kind == 'plan':
        print(f"\n=== Planner (round {data['round']}) ===")
        for i, step in enumerate(data['steps'], 1):
            print(f"  {i}. {step['tool']}("
                  f"{json.dumps(step['arguments'], ensure_ascii=False)})"
                  f" - {step['goal']}")
        if not data['steps']:
            print('  (no steps)')
        if data['note']:
            print(f"  note: {data['note']}")
        for change in data['changes']:
            print(f'  [plan check] {change}')
    elif kind == 'step':
        print(f"\n=== Executor: step {data['index']} ({data['tool']}) ===")
    elif kind.startswith('executor_') and kind[9:] in (
            'tool_call', 'tool_result', 'policy_refused'):
        print_event(kind[9:], data)
    elif kind == 'report':
        print(f"\n=== Reporter (attempt {data['attempt'] + 1}) ===\n"
              f"{data['text']}")
    elif kind == 'review':
        verdict = 'APPROVED' if data['approved'] else 'REJECTED'
        print(f"\n=== Reviewer: {verdict} ===")
        for problem in data['code_problems']:
            print(f'  [code check] {problem}')
        for problem in data['model_problems']:
            print(f'  [model review] {problem}')
    elif kind == 'model_error':
        print(f"[model error] {data['role']}: {data['error']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.
                                     RawDescriptionHelpFormatter)
    parser.add_argument('task', help='What the agent should do.')
    parser.add_argument('--model', default='llama3.1:8b')
    parser.add_argument('--ollama-url', default=None,
                        help='Default: OLLAMA_HOST, localhost, WSL host IP.')
    parser.add_argument('--max-turns', type=int, default=8)
    parser.add_argument('--fake', action='store_true',
                        help='Use fake tools (no Gazebo).')
    parser.add_argument('--multi', action='store_true',
                        help='Planner / executor / reporter / reviewer.')
    parser.add_argument('--review-model', default=None,
                        help='Model for the reviewer (default: --model).')
    args = parser.parse_args()

    tools = build_fake_tools() if args.fake else build_real_tools()
    try:
        model = OllamaChat(model=args.model, base_url=args.ollama_url)
    except ModelError as exc:
        print(f'Cannot reach Ollama: {exc}', file=sys.stderr)
        return 2
    print(f'model={model.name} url={model.base_url} '
          f"tools={'fake' if args.fake else 'real'}"
          f"{' mode=multi' if args.multi else ''}")
    if args.multi:
        reviewer = (OllamaChat(model=args.review_model,
                               base_url=model.base_url)
                    if args.review_model else model)
        multi = run_multi_agent(
            args.task, ToolRegistry(tools), planner=model, executor=model,
            reporter=model, reviewer=reviewer,
            policy=scenario_policy(args.task), on_event=print_multi_event)
        print(f"\n=== Final report ({'approved' if multi.approved else 'NOT approved'}"
              f", {len(multi.reviews)} review round(s)) ===\n{multi.report}")
        return 0 if multi.approved else 1
    result = run_agent(model, ToolRegistry(tools), SYSTEM_PROMPT, args.task,
                       max_turns=args.max_turns, on_event=print_event,
                       policy=scenario_policy(args.task))
    print(f'\n[{result.stop_reason}] turns={result.turns} '
          f'tool_calls={result.tool_calls}')
    return 0 if result.stop_reason == 'final' else 1


if __name__ == '__main__':
    sys.exit(main())
