"""Tests for safe YOLO-triggered search, approach, and action behavior."""

import json

from robot_control.autonomous_controller import AutonomyLogic


IMAGE_SIZE = {'width': 640, 'height': 480}


def payload(*detections):
    return json.dumps({
        'image_size': IMAGE_SIZE,
        'detections': [
            {
                'class_name': name,
                'confidence': confidence,
                'bbox_xyxy': bbox or [250, 80, 390, 420],
            }
            for name, confidence, *optional_bbox in detections
            for bbox in [optional_bbox[0] if optional_bbox else None]
        ],
    })


def test_person_detection_stops_and_preempts_target():
    logic = AutonomyLogic(action_duration=2.0)
    logic.update(payload(('bottle', 0.9)), now=1)
    result = logic.update(
        payload(('bottle', 0.9), ('person', 0.8)), now=1.1)
    assert result == ('person_detected', 0.0, 0.0)
    assert logic.command(now=1.2) == ('person_detected', 0.0, 0.0)


def test_no_target_search_is_slow_and_time_limited():
    logic = AutonomyLogic(search_speed=0.08, search_duration=2.0)
    assert logic.update(payload(), now=1) == ('search_forward', 0.08, 0.0)
    assert logic.update(payload(), now=2.9) == ('search_forward', 0.08, 0.0)
    assert logic.update(payload(), now=3.1) == ('search_timeout', 0.0, 0.0)


def test_target_is_centered_and_approached_before_action():
    logic = AutonomyLogic(approach_speed=0.07)
    small_center_box = [280, 180, 360, 300]
    assert logic.update(
        payload(('bottle', 0.9, small_center_box)), now=1
    ) == ('approach_target', 0.07, 0.0)
    right_box = [450, 120, 550, 440]
    assert logic.update(
        payload(('bottle', 0.9, right_box)), now=1.1
    ) == ('align_to_target', 0.0, -0.25)


def test_target_action_starts_only_when_target_is_close():
    logic = AutonomyLogic(action_duration=1.0, angular_speed=0.7)
    close_box = [250, 80, 390, 420]
    assert logic.update(
        payload(('bottle', 0.9, close_box)), now=1
    ) == ('target_action:turn_left', 0.0, 0.7)
    assert logic.update(
        payload(('bottle', 0.9, close_box)), now=1.9
    )[0] == 'target_action:turn_left'
    assert logic.update(
        payload(('bottle', 0.9, close_box)), now=2.1
    ) == ('target_action_complete', 0.0, 0.0)


def test_target_triggers_only_once_until_it_disappears():
    logic = AutonomyLogic(action_duration=1.0)
    logic.update(payload(('bottle', 0.9)), now=1)
    assert logic.update(payload(('bottle', 0.9)), now=1.5)[0] == 'target_action:turn_left'
    assert logic.update(payload(), now=2.1)[0] == 'search_forward'
    assert logic.update(payload(('bottle', 0.9)), now=2.2)[0] == 'target_action:turn_left'


def test_low_confidence_detection_does_not_trigger_target():
    logic = AutonomyLogic(confidence_threshold=0.5)
    assert logic.update(payload(('person', 0.3), ('bottle', 0.4)), now=1)[0] == 'search_forward'


def test_stale_detection_data_stops_robot():
    logic = AutonomyLogic(stale_timeout=0.5)
    logic.update(payload(('bottle', 0.9)), now=1)
    assert logic.command(now=1.6) == ('stale_detections', 0.0, 0.0)


def test_brief_target_loss_stops_before_resuming_search():
    logic = AutonomyLogic(approach_speed=0.07, search_speed=0.08,
                          target_loss_timeout=0.5)
    small_center_box = [280, 180, 360, 300]
    target = payload(('bottle', 0.9, small_center_box))
    logic.update(target, now=1.0)
    assert logic.update(payload(), now=1.2) == (
        'target_lost_wait', 0.0, 0.0)
    assert logic.update(target, now=1.4)[0] == (
        'approach_target')
    assert logic.update(payload(), now=1.5) == (
        'target_lost_wait', 0.0, 0.0)
    assert logic.update(payload(), now=2.1) == (
        'search_forward', 0.08, 0.0)


def test_malformed_message_cancels_search_and_stops_robot():
    logic = AutonomyLogic()
    logic.update(payload(), now=1)
    assert logic.update('{broken', now=1.1) == ('stop', 0.0, 0.0)
    assert logic.command(now=1.2) == ('stop', 0.0, 0.0)


def test_non_object_json_is_treated_as_invalid_and_safe():
    logic = AutonomyLogic()
    assert logic.update('[]', now=1) == ('stop', 0.0, 0.0)
    assert logic.command(now=1.1) == ('stop', 0.0, 0.0)


def test_brief_loss_after_action_does_not_retrigger_action():
    logic = AutonomyLogic(action_duration=1.0, target_loss_timeout=0.5)
    close_box = [250, 80, 390, 420]
    target = payload(('cup', 0.9, close_box))
    logic.target_class = 'cup'
    logic.update(target, now=1.0)
    assert logic.update(target, now=2.1)[0] == 'target_action_complete'
    assert logic.update(payload(), now=2.2) == ('target_lost_wait', 0.0, 0.0)
    assert logic.update(target, now=2.3) == (
        'target_action_complete', 0.0, 0.0)


def test_person_stop_has_priority_over_close_target_action():
    logic = AutonomyLogic(target_class='cup', approach_speed=0.05)
    close_box = [250, 80, 390, 420]
    assert logic.update(
        payload(('cup', 0.9, close_box), ('person', 0.6)), now=1.0
    ) == ('person_detected', 0.0, 0.0)
    assert logic.command(now=1.05) == ('person_detected', 0.0, 0.0)


def test_cup_target_class_is_case_insensitive():
    logic = AutonomyLogic(target_class='Cup', approach_speed=0.05)
    small_center_box = [280, 180, 360, 300]
    assert logic.update(
        payload(('cup', 0.45, small_center_box)), now=1.0
    ) == ('search_forward', 0.1, 0.0)
    logic = AutonomyLogic(target_class='Cup', approach_speed=0.05,
                          confidence_threshold=0.4)
    assert logic.update(
        payload(('cup', 0.45, small_center_box)), now=1.0
    ) == ('approach_target', 0.05, 0.0)


def test_width_stop_dimension_stops_cropped_target():
    # Wide but short bbox (bottom cropped): height says "far", width "close".
    box = [250, 300, 350, 420]  # width 100/640=0.156, height 120/480=0.25
    by_height = AutonomyLogic(target_class='cup', approach_speed=0.05,
                              stop_bbox_ratio=0.55, target_action='stop')
    assert by_height.update(payload(('cup', 0.8, box)), now=1.0) == (
        'approach_target', 0.05, 0.0)
    by_width = AutonomyLogic(target_class='cup', approach_speed=0.05,
                             stop_bbox_ratio=0.14, target_action='stop',
                             stop_bbox_dimension='width')
    assert by_width.update(payload(('cup', 0.8, box)), now=1.0) == (
        'target_action:stop', 0.0, 0.0)
    assert by_width.update(payload(('cup', 0.8, box)), now=3.0) == (
        'target_action_complete', 0.0, 0.0)


def test_approach_resumes_after_person_leaves():
    logic = AutonomyLogic(target_class='cup', approach_speed=0.05)
    small_center_box = [290, 260, 350, 380]
    cup = ('cup', 0.8, small_center_box)
    person = ('person', 0.7, [100, 100, 200, 470])
    assert logic.update(payload(cup), now=1.0)[0] == 'approach_target'
    assert logic.update(payload(cup, person), now=1.1) == (
        'person_detected', 0.0, 0.0)
    assert logic.update(payload(cup), now=1.2) == (
        'approach_target', 0.05, 0.0)


def test_person_during_action_does_not_restart_action():
    logic = AutonomyLogic(target_class='cup', action_duration=1.0)
    close_box = [250, 80, 390, 420]
    cup = ('cup', 0.9, close_box)
    person = ('person', 0.7, [10, 10, 60, 200])
    assert logic.update(payload(cup), now=1.0)[0] == 'target_action:turn_left'
    assert logic.update(payload(cup, person), now=1.2)[0] == 'person_detected'
    assert logic.update(payload(cup), now=1.3) == (
        'target_action_complete', 0.0, 0.0)
