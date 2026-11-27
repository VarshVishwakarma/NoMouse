from pathlib import Path

import numpy as np
import pytest


def test_bundled_tasks_model_initializes_and_processes_a_frame():
    pytest.importorskip("mediapipe")
    from nomouse.tracker import HandTracker

    model = Path(__file__).parents[1] / "nomouse" / "models" / "hand_landmarker.task"
    assert model.is_file()
    tracker = HandTracker()
    try:
        observations, result = tracker.process(np.zeros((240, 320, 3), dtype=np.uint8))
        assert len(observations) == len(result.hand_landmarks)
        assert tracker.last_inference_ms >= 0.0
    finally:
        tracker.close()
