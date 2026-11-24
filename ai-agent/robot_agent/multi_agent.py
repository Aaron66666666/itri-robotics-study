"""Multi-agent pipeline: Planner -> Executor -> Reporter -> Reviewer.

Roles (each is a separate model call with its own instructions):
  Planner   structured JSON plan; checked in code before anything runs
  Executor  the tool-calling loop (loop.py), one plan step at a time
  Reporter  writes the report from the collected evidence only (no tools)
  Reviewer  code checks the facts (numbers, PASS/FAIL, check results must
            match the evidence); the model only checks coverage (is every
            part of the request answered?). Rejected reports go back to the
            Reporter with the problems, at most `max_revisions` times.

The roles can use different models; by default they share one.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .llm import ChatModel, ModelError
from .loop import Policy, run_agent
from .messages import Message
from .tools import ToolRegistry, validate_arguments

MAX_STEPS = 5
MAX_PLAN_ROUNDS = 3

PLANNER_PROMPT = """You are the planner in a team that tests a ROS 2 / \
Gazebo robot. You do not run tools yourself; you write a plan that an \
executor will carry out.

Available tools (name, description, arguments as JSON schema):
{tools}

Rules:
- Use the smallest number of steps that answers the request. One step = one \
tool call. Never repeat the same call.
- Only run scenarios the user explicitly asked for. If the user asks for a \
scenario or run that does not exist, make no step for it and explain in \
"note".
- If you need a saved run but do not know its exact name, plan \
get_run_summary with your best guess; the executor looks up the exact name \
if the guess is wrong.
- If EVIDENCE is given, those steps were already executed. Plan only what \
is still needed to answer the request (never repeat a step). If nothing \
more is needed, return no steps and "done": true.
- Return JSON only: {{"steps": [{{"tool": ..., "arguments": {{...}}, \
"goal": ...}}], "note": ..., "done": true/false}}."""

EXECUTOR_PROMPT = """You are the executor in a robot test team. Carry out \
exactly one plan step by calling the tool it names. If the tool returns an \
error, use the error message to fix the arguments (for example call \
list_saved_runs to find an exact run name) and try again. Do nothing beyond \
this step. When the step is done, reply with one short sentence."""

REPORTER_PROMPT = """You are the reporter in a robot test team. Write the \
final report for the user from the EVIDENCE only (results returned by the \
tools).
- Answer every part of the user's request.
- Every number you write must appear in the evidence. Never estimate, \
round differently or invent numbers.
- State PASS/FAIL exactly as the evidence says, and name any failed check.
- If the evidence does not contain something the user asked for, say so.
- Write in Traditional Chinese (繁體中文, Taiwan usage); keep tool, \
scenario, run and check names in English. Be concise."""

REVIEWER_PROMPT = """You are the reviewer in a robot test team. Facts \
(numbers, PASS/FAIL, check results) are verified separately by code; your \
only job is COVERAGE.
Step 1: split the USER REQUEST into the separate things it asks for (usually \
1-3 parts).
Step 2: for each part, decide whether the REPORT answers it. A part is \
answered if the report gives that information, or clearly says the evidence \
does not contain it. Extra details in the report do not matter.
Return JSON only: {"parts": [{"part": ..., "answered": true/false}]}."""

REVIEW_SCHEMA = {
    'type': 'object',
    'properties': {'parts': {'type': 'array', 'items': {
        'type': 'object',
        'properties': {'part': {'type': 'string'},
                       'answered': {'type': 'boolean'}},
        'required': ['part', 'answered']}}},
    'required': ['parts'],
}


def missing_parts(review: dict) -> list[str]:
    """Parts the reviewer marked unanswered (approval is decided in code)."""
    return [str(p.get('part', '')) for p in review.get('parts') or []
            if isinstance(p, dict) and not p.get('answered')]


PASS_WORDS = ('PASS', '通過', '成功', 'true', 'True')
VERDICT_WORDS = ('PASS', 'FAIL', '通過', '失敗')
NEGATIONS = ('無法', '沒有', '未', '不能', '尚無', 'not', 'cannot', 'no ')
FAIL_WORDS = ('FAIL', '未通過', '沒通過', '不通過', '失敗', 'false', 'False')

NUM_RE = re.compile(r'(?<![A-Za-z0-9_.])-?\d+(?:\.\d+)?(?![A-Za-z0-9_]|\.\d)')
ANY_NUM_RE = re.compile(r'\d+(?:\.\d+)?')


@dataclass
class MultiAgentResult:
    plan: list[dict]
    plan_note: str
    plan_changes: list[str]
    evidence: list[dict]
    report: str
    approved: bool
    reviews: list[dict] = field(default_factory=list)
    stop_reason: str = 'done'  # 'done' | 'model_error'


# ------------------------------------------------------------ planner
def plan_schema(tool_names: list[str]) -> dict:
    return {
        'type': 'object',
        'properties': {
            'steps': {'type': 'array', 'items': {
                'type': 'object',
                'properties': {
                    'tool': {'type': 'string', 'enum': tool_names},
                    'arguments': {'type': 'object'},
                    'goal': {'type': 'string'}},
                'required': ['tool', 'arguments', 'goal']}},
            'note': {'type': 'string'},
            'done': {'type': 'boolean'}},
        'required': ['steps'],
    }


def check_plan(raw: dict, registry: ToolRegistry, policy: Policy | None,
               done_keys: set[str] | None = None
               ) -> tuple[list[dict], list[str]]:
    """Code-side plan validation: known tools, policy, no duplicates, cap.

    Returns the accepted steps and a list of human-readable changes.
    Invalid arguments are kept (the executor can repair them from the
    tool's error message); unknown tools and policy refusals are dropped.
    """
    steps, changes, seen = [], [], set(done_keys or ())
    for step in raw.get('steps') or []:
        if not isinstance(step, dict):
            continue
        tool = step.get('tool')
        args = step.get('arguments') or {}
        if not isinstance(args, dict):
            args = {}
        if tool not in registry.tools:
            changes.append(f'dropped step with unknown tool "{tool}"')
            continue
        refusal = policy(tool, args) if policy else None
        if refusal:
            changes.append(f'dropped {tool}({args}): {refusal}')
            continue
        key = tool + json.dumps(args, sort_keys=True, ensure_ascii=False)
        if key in seen:
            changes.append(f'dropped repeated step {tool}({args})')
            continue
        seen.add(key)
        problems = validate_arguments(registry.tools[tool].parameters, args)
        if problems:
            changes.append(f'{tool}({args}) has invalid arguments '
                           f'({"; ".join(problems)}); executor will repair')
        steps.append({'tool': tool, 'arguments': args,
                      'goal': str(step.get('goal', ''))})
    if len(steps) > MAX_STEPS:
        changes.append(f'plan cut from {len(steps)} to {MAX_STEPS} steps')
        steps = steps[:MAX_STEPS]
    return steps, changes


# ----------------------------------------------------------- reviewer
def _numbers_in(value: Any, out: list[float]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        out.append(float(value))
    elif isinstance(value, str):
        out.extend(float(n) for n in ANY_NUM_RE.findall(value))
    elif isinstance(value, dict):
        for item in value.values():
            _numbers_in(item, out)
    elif isinstance(value, list):
        for item in value:
            _numbers_in(item, out)


def unsupported_numbers(report: str, evidence: list[dict],
                        request: str) -> list[str]:
    """Numbers in the report that appear neither in the evidence nor in the
    request. Integers 0-10 are ignored (counts, list numbering)."""
    known: list[float] = []
    _numbers_in([e.get('result') for e in evidence], known)
    _numbers_in(request, known)
    missing = []
    for text in NUM_RE.findall(report):
        value = float(text)
        if value.is_integer() and 0 <= value <= 10:
            continue
        decimals = len(text.split('.')[1]) if '.' in text else 0
        if not any(abs(value - k) < 1e-9 or round(k, decimals) == value
                   for k in known):
            missing.append(text)
    return sorted(set(missing), key=missing.index)


def _claimed(line: str) -> bool | None:
    """True/False if the line states PASS/FAIL, None if it states neither."""
    if any(word in line for word in FAIL_WORDS):
        return False
    if any(word in line for word in PASS_WORDS):
        return True
    return None


def contradicted_claims(report: str, evidence: list[dict]) -> list[str]:
    """PASS/FAIL statements that contradict the evidence.

    Per report line: a check name next to PASS/FAIL must match that check's
    true/false; a run or scenario name next to PASS/FAIL (without a check
    name) must match its verdict. A claim is accepted if any evidence entry
    matches it (several runs may share check names).
    """
    checks: dict[str, set[bool]] = {}
    verdicts: dict[str, set[bool]] = {}
    for item in evidence:
        result = item.get('result')
        if not isinstance(result, dict):
            continue
        for name, value in (result.get('checks') or {}).items():
            checks.setdefault(name, set()).add(bool(value))
        if 'verdict' in result:
            ok = result['verdict'] == 'PASS'
            for key in ('run', 'scenario'):
                if result.get(key):
                    verdicts.setdefault(str(result[key]), set()).add(ok)
    problems = []
    if not checks and not verdicts:
        # Nothing was tested, so no PASS/FAIL statement can be true.
        # Only assertions count: "無法得出 PASS 或 FAIL" is a correct
        # statement, "答案是：PASS" is not.
        found = sorted({word for line in report.splitlines()
                        if not any(neg in line for neg in NEGATIONS)
                        for word in VERDICT_WORDS if word in line})
        if found:
            problems.append(
                f'No test was run, so the report must not contain the words '
                f'{", ".join(found)}. Rewrite it without them: describe what '
                'the tools returned (or that nothing could be run) in plain '
                'words.')
        return problems
    for line in report.splitlines():
        claim = _claimed(line)
        if claim is None:
            continue
        named_checks = [n for n in checks if n in line]
        for name in named_checks:
            if claim not in checks[name]:
                problems.append(f'Correct check {name}: the report says '
                                f'{"PASS" if claim else "FAIL"}, but the '
                                f'evidence says {not claim}.')
        if named_checks:
            continue
        for name, values in verdicts.items():
            if name in line and claim not in values:
                problems.append(f'Correct {name}: the report says '
                                f'{"PASS" if claim else "FAIL"}, but its '
                                'verdict in the evidence is '
                                f'{"PASS" if not claim else "FAIL"}.')
    return problems


def _evidence_text(evidence: list[dict]) -> str:
    return json.dumps([{'tool': e['tool'], 'arguments': e['arguments'],
                        'ok': e['ok'], 'result': e['result']}
                       for e in evidence], ensure_ascii=False, indent=1)


# ------------------------------------------------------- orchestrator
def run_multi_agent(request: str, registry: ToolRegistry, *,
                    planner: ChatModel, executor: ChatModel,
                    reporter: ChatModel, reviewer: ChatModel,
                    policy: Policy | None = None, max_revisions: int = 2,
                    on_event: Callable[[str, dict], None] | None = None
                    ) -> MultiAgentResult:
    emit = on_event or (lambda kind, data: None)
    tool_text = json.dumps(registry.schemas(), ensure_ascii=False)

    # 1-2. plan -> execute -> re-plan with the evidence (plan-and-execute)
    evidence: list[dict] = []
    pending: dict[str, Any] = {}
    all_steps: list[dict] = []
    all_changes: list[str] = []
    done_keys: set[str] = set()
    note = ''

    def collect(kind: str, data: dict) -> None:
        if kind == 'tool_call':
            pending['call'] = data
        elif kind == 'tool_result':
            call = pending.pop('call', {})
            try:
                result = json.loads(data['content'])
            except json.JSONDecodeError:
                result = data['content']
            args = call.get('arguments', {})
            done_keys.add(data['name'] + json.dumps(
                args, sort_keys=True, ensure_ascii=False))
            evidence.append({'tool': data['name'], 'arguments': args,
                             'ok': data['ok'], 'result': result})
        emit(f'executor_{kind}', data)

    for round_no in range(1, MAX_PLAN_ROUNDS + 1):
        user = request if not evidence else (
            f'{request}\n\nEVIDENCE (steps already executed):\n'
            f'{_evidence_text(evidence)}')
        try:
            raw = planner.chat_json(
                [Message('system', PLANNER_PROMPT.format(tools=tool_text)),
                 Message('user', user)],
                plan_schema(sorted(registry.tools)))
        except ModelError as exc:
            emit('model_error', {'role': 'planner', 'error': str(exc)})
            return MultiAgentResult(all_steps, note, all_changes, evidence,
                                    str(exc), False,
                                    stop_reason='model_error')
        steps, changes = check_plan(raw, registry, policy, done_keys)
        steps = steps[:max(0, MAX_STEPS - len(all_steps))]
        note = str(raw.get('note') or note)
        all_changes += changes
        emit('plan', {'round': round_no, 'steps': steps, 'note': note,
                      'changes': changes})
        if not steps:
            break
        for step in steps:
            all_steps.append(step)
            index = len(all_steps)
            emit('step', {'index': index, **step})
            task = (f'User request: {request}\n'
                    f'Your step ({index}): {step["goal"]}\n'
                    f'Call: {step["tool"]}('
                    f'{json.dumps(step["arguments"], ensure_ascii=False)})')
            result = run_agent(executor, registry, EXECUTOR_PROMPT, task,
                               max_turns=4, on_event=collect, policy=policy)
            if result.stop_reason == 'model_error':
                return MultiAgentResult(all_steps, note, all_changes,
                                        evidence, result.final_text, False,
                                        stop_reason='model_error')
        if raw.get('done') is True or len(all_steps) >= MAX_STEPS:
            break
    steps, changes = all_steps, all_changes

    # 3. report + 4. review, with revisions
    evidence_text = (_evidence_text(evidence) if evidence else
                     '(none: no tool was run, so there are no test results)')
    context = (f'USER REQUEST:\n{request}\n\nPLANNER NOTE:\n{note or "-"}'
               f'\n\nEVIDENCE (tool results):\n{evidence_text}')
    reviews: list[dict] = []
    report, feedback = '', []
    for attempt in range(max_revisions + 1):
        prompt = context
        if feedback:
            prompt += ('\n\nYOUR PREVIOUS REPORT:\n' + report +
                       '\n\nTHE REVIEWER FOUND THESE PROBLEMS; fix them:\n- '
                       + '\n- '.join(feedback))
        try:
            report = reporter.chat([Message('system', REPORTER_PROMPT),
                                    Message('user', prompt)], []).content
            emit('report', {'attempt': attempt, 'text': report})
            code_problems = [
                f'Remove or correct the number {n}: it does not appear in '
                'the evidence.'
                for n in unsupported_numbers(report, evidence, request)]
            code_problems += contradicted_claims(report, evidence)
            review = reviewer.chat_json(
                [Message('system', REVIEWER_PROMPT),
                 Message('user', f'{context}\n\nREPORT:\n{report}')],
                REVIEW_SCHEMA)
        except ModelError as exc:
            emit('model_error', {'role': 'reporter/reviewer',
                                 'error': str(exc)})
            return MultiAgentResult(steps, note, changes, evidence, report,
                                    False, reviews, 'model_error')
        model_problems = [f'Not answered: {p}' for p in missing_parts(review)]
        model_ok = bool(review.get('parts')) and not model_problems
        approved = model_ok and not code_problems
        record = {'attempt': attempt, 'approved': approved,
                  'code_problems': code_problems,
                  'model_approved': model_ok,
                  'model_problems': model_problems}
        reviews.append(record)
        emit('review', record)
        if approved:
            return MultiAgentResult(steps, note, changes, evidence, report,
                                    True, reviews)
        feedback = code_problems + model_problems
    return MultiAgentResult(steps, note, changes, evidence, report, False,
                            reviews)
