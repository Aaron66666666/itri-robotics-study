import importlib.util
from pathlib import Path

from camera_subscriber import (
    DEFAULT_YOLO_MODEL, MODEL_DIR, resolve_model_path, YOLO_MODELS)
from launch.actions import DeclareLaunchArgument
from launch.launch_context import LaunchContext
import pytest

LAUNCH_DIR = Path(__file__).resolve().parents[1] / 'launch'


def test_named_models_resolve_to_their_files():
    assert resolve_model_path('v3') == str(MODEL_DIR / 'yolo26n_gazebo_v3.pt')
    assert resolve_model_path('v5') == str(
        MODEL_DIR / 'yolo26n_gazebo_v5clean.pt')
    assert resolve_model_path('coco') == str(MODEL_DIR / 'yolo26n.pt')


def test_default_is_still_v3():
    assert DEFAULT_YOLO_MODEL == 'v3'
    assert resolve_model_path(DEFAULT_YOLO_MODEL, '').endswith(
        'yolo26n_gazebo_v3.pt')


def test_model_path_overrides_the_name():
    path = resolve_model_path('v5', '~/weights/other.pt')
    assert path == str(Path.home() / 'weights' / 'other.pt')


def test_unknown_name_is_rejected():
    with pytest.raises(ValueError, match='v3, v5, coco'):
        resolve_model_path('v4')


@pytest.mark.parametrize('name', [
    'camera_yolo.launch.py', 'autonomous_yolo.launch.py'])
def test_launch_choices_match_the_node(name):
    spec = importlib.util.spec_from_file_location(
        name.replace('.', '_'), LAUNCH_DIR / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    args = {a.name: a for a in module.generate_launch_description().entities
            if isinstance(a, DeclareLaunchArgument)}
    yolo_model = args['yolo_model']
    assert yolo_model.choices == list(YOLO_MODELS)
    context = LaunchContext()
    default = ''.join(s.perform(context) for s in yolo_model.default_value)
    assert default == DEFAULT_YOLO_MODEL
    assert ''.join(
        s.perform(context) for s in args['model_path'].default_value) == ''
