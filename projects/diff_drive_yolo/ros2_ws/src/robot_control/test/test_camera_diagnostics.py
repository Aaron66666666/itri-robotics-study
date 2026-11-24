from camera_subscriber import save_diagnostic_frame
import cv2
import numpy as np
import pytest


def test_diagnostic_frame_is_lossless(tmp_path):
    frame = np.zeros((24, 32, 3), dtype=np.uint8)
    frame[3:20, 5:27] = (17, 83, 241)
    path = tmp_path / 'camera.png'

    save_diagnostic_frame(frame, path)

    saved = cv2.imread(str(path), cv2.IMREAD_COLOR)
    assert saved is not None
    assert np.array_equal(saved, frame)


def test_diagnostic_frame_does_not_overwrite(tmp_path):
    path = tmp_path / 'camera.png'
    path.write_bytes(b'keep this data')

    with pytest.raises(FileExistsError):
        save_diagnostic_frame(np.zeros((2, 2, 3), dtype=np.uint8), path)

    assert path.read_bytes() == b'keep this data'


def test_diagnostic_frame_requires_png(tmp_path):
    with pytest.raises(ValueError, match='end in .png'):
        save_diagnostic_frame(
            np.zeros((2, 2, 3), dtype=np.uint8), tmp_path / 'camera.jpg')
