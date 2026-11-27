from nomouse.gestures import GestureConsensus, classify_hand
from nomouse.types import Gesture, HandObservation


def test_consensus_rejects_single_frame_noise():
    c = GestureConsensus(window=5, required_frames=3)
    for _ in range(3):
        current = c.update(Gesture.POINT)
    assert current == Gesture.POINT
    assert c.update(Gesture.PINCH) == Gesture.POINT
    assert c.update(Gesture.POINT) == Gesture.POINT


def test_consensus_switches_after_confirmed_transition():
    c = GestureConsensus(window=5, required_frames=3)
    for _ in range(3):
        current = c.update(Gesture.TWO_FINGERS)
    assert current == Gesture.TWO_FINGERS
    for _ in range(3):
        current = c.update(Gesture.THREE_FINGERS)
    assert current == Gesture.THREE_FINGERS


def test_single_unknown_frame_preserves_confirmed_pose_but_is_not_actionable_by_app():
    c = GestureConsensus(window=5, required_frames=3, unknown_grace_frames=1)
    for _ in range(3):
        c.update(Gesture.POINT)
    assert c.update(Gesture.UNKNOWN) == Gesture.POINT
    assert c.current == Gesture.POINT


def test_sustained_unknown_resets_consensus_after_grace():
    c = GestureConsensus(window=5, required_frames=3, unknown_grace_frames=1)
    for _ in range(3):
        c.update(Gesture.POINT)
    assert c.update(Gesture.UNKNOWN) == Gesture.POINT
    assert c.update(Gesture.UNKNOWN) == Gesture.UNKNOWN
    assert len(c.history) == 0


def test_critical_gestures_can_have_different_confirmation_thresholds():
    c = GestureConsensus(window=5, required_frames=2, required_by_gesture={Gesture.TWO_FINGERS: 4})
    for _ in range(2):
        current = c.update(Gesture.POINT)
    for _ in range(3):
        current = c.update(Gesture.TWO_FINGERS)
    assert current == Gesture.POINT
    current = c.update(Gesture.TWO_FINGERS)
    assert current == Gesture.TWO_FINGERS


def _synthetic_hand(four_fingers=True, thumb_open=False):
    """Create coherent 21-point landmarks for deterministic finger-shape tests."""
    points = [(0.50, 0.82, 0.0) for _ in range(21)]
    # Palm landmarks.
    points[0] = (0.50, 0.82, 0.0)   # wrist
    points[1] = (0.43, 0.70, 0.0)
    points[2] = (0.39, 0.65, 0.0)   # thumb MCP
    points[3] = (0.34, 0.60, 0.0)
    points[4] = (0.28, 0.54, 0.0) if thumb_open else (0.49, 0.63, 0.0)
    finger_data = {
        # mcp, pip, dip, tip, x
        "index": (5, 6, 7, 8, 0.40),
        "middle": (9, 10, 11, 12, 0.48),
        "ring": (13, 14, 15, 16, 0.56),
        "pinky": (17, 18, 19, 20, 0.64),
    }
    for name, (mcp, pip, dip, tip, x) in finger_data.items():
        points[mcp] = (x, 0.58, 0.0)
        if four_fingers or name in ("index", "middle", "ring"):
            points[pip] = (x, 0.43, 0.0)
            points[dip] = (x, 0.27, 0.0)
            points[tip] = (x, 0.10, 0.0)
        else:
            # A bent pinky with a clear ~90 degree joint angle.
            points[pip] = (x, 0.44, 0.0)
            points[dip] = (x + 0.045, 0.49, 0.0)
            points[tip] = (x + 0.08, 0.45, 0.0)
    return HandObservation(tuple(points))


def test_four_fingers_with_tucked_thumb_is_browser_back_gesture():
    assert classify_hand(_synthetic_hand(four_fingers=True, thumb_open=False)) == Gesture.FOUR_FINGERS


def test_four_fingers_with_thumb_out_is_open_palm_not_browser_back():
    assert classify_hand(_synthetic_hand(four_fingers=True, thumb_open=True)) == Gesture.OPEN_PALM


def _synthetic_pinch_hand(touching=True):
    """Build a hand whose index is bent while thumb/index tips touch (or separate)."""
    p = [(0.50, 0.80, 0.0) for _ in range(21)]
    # Thumb points; tip 4 is close to tip 8 only in the deliberate pinch pose.
    p[0] = (0.50, 0.88, 0.0)
    p[1] = (0.47, 0.77, 0.0)
    p[2] = (0.45, 0.70, 0.0)
    p[3] = (0.47, 0.62, 0.0)
    p[4] = (0.50, 0.55, 0.0) if touching else (0.32, 0.67, 0.0)
    # Bent index: joint angles are deliberately below the extension threshold.
    p[5] = (0.42, 0.62, 0.0)
    p[6] = (0.42, 0.50, 0.0)
    p[7] = (0.48, 0.48, 0.0)
    p[8] = (0.50, 0.55, 0.0) if touching else (0.50, 0.66, 0.0)
    # Folded middle, ring, and pinky fingers.
    for mcp, pip, dip, tip, x in (
        (9, 10, 11, 12, 0.50),
        (13, 14, 15, 16, 0.57),
        (17, 18, 19, 20, 0.64),
    ):
        p[mcp] = (x, 0.63, 0.0)
        p[pip] = (x, 0.53, 0.0)
        p[dip] = (x + 0.045, 0.54, 0.0)
        p[tip] = (x + 0.085, 0.60, 0.0)
    return HandObservation(tuple(p))


def test_bent_index_thumb_index_contact_is_pinch_not_fist():
    assert classify_hand(_synthetic_pinch_hand(touching=True)) == Gesture.PINCH


def test_separated_thumb_and_index_with_curled_fingers_is_fist():
    assert classify_hand(_synthetic_pinch_hand(touching=False)) == Gesture.FIST


def test_gesture_transition_requires_consecutive_frames_not_accumulated_votes():
    c = GestureConsensus(window=5, required_frames=2)
    c.update(Gesture.POINT)
    assert c.update(Gesture.POINT) == Gesture.POINT
    assert c.update(Gesture.PINCH) == Gesture.POINT
    assert c.update(Gesture.POINT) == Gesture.POINT  # cancels pending pinch
    assert c.update(Gesture.PINCH) == Gesture.POINT
    assert c.update(Gesture.PINCH) == Gesture.PINCH


def test_malformed_landmark_count_returns_unknown_instead_of_crashing():
    assert classify_hand(HandObservation(tuple([(0.5, 0.5, 0.0)] * 20))) == Gesture.UNKNOWN


def test_pinch_threshold_is_configurable_and_bounded():
    points = list(_synthetic_pinch_hand(touching=True).landmarks)
    points[4] = (points[4][0] + 0.06, points[4][1], points[4][2])
    hand = HandObservation(tuple(points))
    assert classify_hand(hand, pinch_threshold=0.34) == Gesture.PINCH
    assert classify_hand(hand, pinch_threshold=0.20) == Gesture.FIST
    assert classify_hand(hand, pinch_threshold=3.0) == Gesture.PINCH
