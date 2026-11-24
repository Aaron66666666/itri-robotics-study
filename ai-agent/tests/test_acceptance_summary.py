"""Real summarizer on the saved 2026-11-24 evidence runs (no Gazebo)."""

from pathlib import Path

import pytest

from robot_agent.acceptance_tools import get_run_summary, summarize_run

EVIDENCE = (Path(__file__).resolve().parents[2] / 'projects' /
            'diff_drive_yolo' / 'docs' / 'evidence' / '2026-11-24')
pytestmark = pytest.mark.skipif(not EVIDENCE.is_dir(),
                                reason='evidence files not present')


def test_person_stop_run_on_cpu_passes_with_measured_latency():
    s = summarize_run('D1_person', EVIDENCE)
    assert s['scenario'] == 'person_stop' and s['verdict'] == 'PASS'
    assert s['facts']['person_to_stop_ms'] == 94
    assert s['facts']['moved_while_person_visible_m'] < 0.01
    assert s['yolo_device'] == 'cpu'
    assert s['max_confidence_by_class']['person'] > 0.9


def test_person_stop_run_on_gpu_passes():
    s = summarize_run('D3_person_gpu', EVIDENCE)
    assert s['verdict'] == 'PASS' and s['yolo_device'] == 'cuda:0'
    assert s['facts']['person_left_to_resume_ms'] == 52


def test_approach_run_passes():
    s = summarize_run('A1_approach', EVIDENCE)
    assert s['scenario'] == 'approach' and s['verdict'] == 'PASS'
    assert 0.5 < s['final_x_m'] < 0.55


def test_target_loss_run_passes():
    s = summarize_run('B1_loss', EVIDENCE)
    assert s['scenario'] == 'target_loss' and s['verdict'] == 'PASS'
    assert {'saw_target_lost_wait', 'saw_search_forward',
            'saw_search_timeout'} <= set(s['checks'])


def test_bad_run_name_is_rejected():
    with pytest.raises(ValueError):
        get_run_summary('../etc/passwd')
