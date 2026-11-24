#!/usr/bin/env python3
"""Compare local models on fixed agent tasks with the fake tools.

For each model and task it checks, automatically:
  calls     - the required tool calls were made (name + argument subset)
  forbidden - no forbidden call was made (e.g. running a non-existent scenario)
  answer    - the final answer contains the facts from the tool results
  zh_tw     - the answer is Traditional Chinese (no Simplified-only characters)

Usage:
  python3 eval_models.py                       # qwen2.5:7b and llama3.1:8b
  python3 eval_models.py --models qwen2.5:7b --repeat 3
Results: eval_results/<timestamp>.json and a printed table.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from robot_agent import fake_tools  # noqa: E402
from robot_agent.acceptance_tools import scenario_policy  # noqa: E402
from robot_agent.fake_tools import build_fake_tools  # noqa: E402
from robot_agent.llm import OllamaChat  # noqa: E402
from robot_agent.loop import run_agent  # noqa: E402
from robot_agent.prompts import SYSTEM_PROMPT  # noqa: E402
from robot_agent.tools import ToolRegistry  # noqa: E402

# Characters that exist only in Simplified Chinese (their Traditional forms
# differ), common in this domain. Any of them means the answer drifted.
SIMPLIFIED_ONLY = set('们这说运场关键结车辆为过时检测么问题个对没还发现样经'
                      '进过让门实现应该数据显示执败续员态览较')

TASKS = [
    {'id': 'list',
     'task': '列出可用的驗收情境。',
     'calls': [('list_scenarios', {})],
     'answer_all': ['approach', 'target_loss', 'person_stop']},
    {'id': 'run_person_gpu',
     'task': '用 GPU 執行 person_stop，回報是否通過與停車反應時間。',
     'calls': [('run_scenario', {'scenario': 'person_stop'})],
     'answer_all': ['94'], 'answer_any': ['PASS', '通過']},
    {'id': 'gpu',
     'task': '現在 GPU 能用嗎？',
     'calls': [('get_gpu_status', {})],
     'answer_any': ['4070', 'CUDA', 'cuda']},
    {'id': 'failure',
     'fail': {'approach'},
     'task': '執行 approach 情境並告訴我結果，若失敗請說明哪一項檢查沒過。',
     'calls': [('run_scenario', {'scenario': 'approach'})],
     'answer_all': ['reached_target_and_stopped'],
     'answer_any': ['FAIL', '失敗', '未通過']},
    {'id': 'saved_run',
     'task': '摘要已保存的 person_stop 執行紀錄。',
     'calls': [('get_run_summary', {'run_name': 'D1_person'})],
     'answer_any': ['PASS', '通過']},
    {'id': 'unknown_scenario',
     'task': '執行 fly_to_moon 情境。',
     'calls': [],
     'forbidden': ['run_scenario'],
     # Correct behaviour: refuse and say the scenario does not exist.
     'answer_any': ['不存在', '沒有', '無法', 'not', '不支援', '找不到',
                    '並無', '未提供', '不在', '不正確', '不是有效']},
]


def check(task: dict, result, calls: list) -> dict:
    answer = result.final_text or ''
    made = [(name, args) for name, args in calls]

    def has_call(name, subset):
        return any(n == name and all(a.get(k) == v for k, v in subset.items())
                   for n, a in made)
    ok_calls = all(has_call(n, s) for n, s in task['calls'])
    ok_forbidden = not any(n in task.get('forbidden', []) for n, _ in made)
    ok_answer = (result.stop_reason == 'final'
                 and all(s in answer for s in task.get('answer_all', []))
                 and (not task.get('answer_any')
                      or any(s in answer for s in task['answer_any'])))
    simplified = sorted({c for c in answer if c in SIMPLIFIED_ONLY})
    return {'calls': ok_calls, 'forbidden': ok_forbidden,
            'answer': ok_answer, 'zh_tw': not simplified,
            'simplified_chars': ''.join(simplified)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', nargs='+',
                        default=['qwen2.5:7b', 'llama3.1:8b'])
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--max-turns', type=int, default=6)
    args = parser.parse_args()

    records = []
    for model_name in args.models:
        model = OllamaChat(model=model_name)
        model.chat([], [])  # warm-up: load the model onto the GPU first
        for rep in range(args.repeat):
            for task in TASKS:
                fake_tools.CALL_LOG.clear()
                fake_tools.FAIL_SCENARIOS.clear()
                fake_tools.FAIL_SCENARIOS.update(task.get('fail', set()))
                start = time.time()
                result = run_agent(model, ToolRegistry(build_fake_tools()),
                                   SYSTEM_PROMPT, task['task'],
                                   max_turns=args.max_turns,
                                   policy=scenario_policy(task['task']))
                checks = check(task, result, list(fake_tools.CALL_LOG))
                record = {'model': model_name, 'task': task['id'],
                          'repeat': rep, 'stop_reason': result.stop_reason,
                          'turns': result.turns,
                          'tool_calls': [n for n, _ in fake_tools.CALL_LOG],
                          'seconds': round(time.time() - start, 1),
                          'passed': all(v for k, v in checks.items()
                                        if k != 'simplified_chars'),
                          **checks, 'answer': result.final_text}
                records.append(record)
                flags = ' '.join(f"{k}={'ok' if checks[k] else 'X'}"
                                 for k in ('calls', 'forbidden', 'answer',
                                           'zh_tw'))
                print(f"{model_name:12s} {task['id']:17s} "
                      f"{'PASS' if record['passed'] else 'FAIL'}  {flags}  "
                      f"turns={result.turns} {record['seconds']}s "
                      f"calls={record['tool_calls']}", flush=True)

    out = Path(__file__).resolve().parent / 'eval_results'
    out.mkdir(exist_ok=True)
    path = out / f"{time.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(records, ensure_ascii=False, indent=1))
    print('\nmodel         passed/total  avg_seconds')
    for model_name in args.models:
        rows = [r for r in records if r['model'] == model_name]
        passed = sum(r['passed'] for r in rows)
        avg = sum(r['seconds'] for r in rows) / len(rows)
        print(f'{model_name:12s}  {passed}/{len(rows)}          {avg:.1f}')
    print(f'saved {path}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
