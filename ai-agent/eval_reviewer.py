#!/usr/bin/env python3
"""Measure how well each model judges report COVERAGE (the reviewer's job).

8 labeled cases: 4 reports that answer every part of the request, 4 that
miss one part. Reports whether each model approves/rejects correctly.
Usage: python3 eval_reviewer.py [--models ...] [--repeat N]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from robot_agent.llm import OllamaChat  # noqa: E402
from robot_agent.messages import Message  # noqa: E402
from robot_agent.multi_agent import (  # noqa: E402
    REVIEW_SCHEMA, REVIEWER_PROMPT, missing_parts)

CASES = [  # (request, report, should_approve)
    ('用 GPU 執行 person_stop，回報是否通過與停車反應時間。',
     'person_stop：PASS。停車反應時間 94 ms。', True),
    ('用 GPU 執行 person_stop，回報是否通過與停車反應時間。',
     'person_stop：PASS。所有檢查都通過。', False),
    ('現在 GPU 能用嗎？', 'GPU 可以使用：RTX 4070，PyTorch CUDA 為 True。', True),
    ('比較 D1_person 和 D3_person_gpu 的停車反應時間與推論時間。',
     'D1_person：停車 94 ms，推論 27 ms。D3_person_gpu：停車 93 ms，推論 20 ms。',
     True),
    ('比較 D1_person 和 D3_person_gpu 的停車反應時間與推論時間。',
     'D1_person：停車 94 ms。D3_person_gpu：停車 93 ms。', False),
    ('執行 approach，若失敗請說明哪一項檢查沒過。',
     'approach：FAIL，未通過的檢查為 reached_target_and_stopped。', True),
    ('執行 approach，若失敗請說明哪一項檢查沒過。', 'approach：FAIL。', False),
    ('列出可用的驗收情境與每個情境的用途。',
     '可用情境：approach、target_loss、person_stop。', False),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--models', nargs='+',
                        default=['llama3.1:8b', 'qwen2.5:7b'])
    parser.add_argument('--repeat', type=int, default=2)
    args = parser.parse_args()
    for name in args.models:
        model = OllamaChat(model=name)
        correct = false_reject = false_approve = 0
        for _ in range(args.repeat):
            for request, report, should in CASES:
                review = model.chat_json(
                    [Message('system', REVIEWER_PROMPT),
                     Message('user', f'USER REQUEST:\n{request}\n\n'
                                     f'REPORT:\n{report}')], REVIEW_SCHEMA)
                approved = (bool(review.get('parts'))
                            and not missing_parts(review))
                correct += approved == should
                false_reject += should and not approved
                false_approve += approved and not should
        total = len(CASES) * args.repeat
        print(f'{name:12s} correct {correct}/{total}  '
              f'false_reject {false_reject}  false_approve {false_approve}')


if __name__ == '__main__':
    main()
