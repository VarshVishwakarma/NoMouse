"""End-to-end tests of the gesture pipeline: synthetic hands in, fake mouse events out."""
import pytest

from nomouse.app import GesturePipeline
from nomouse.config import AppConfig
from nomouse.controller import MouseController
from nomouse.types import Gesture, HandObservation
from tests.support import (
    FakeMouse,
    SafeGuard,
    fist_hand,
    pinch_hand,
    pointing_hand,
    translate,
    two_finger_hand,
)

SCREEN = (1920, 1080)
DT = 1.0 / 30.0


class Rig:
    """Drives a pipeline at 30 fps with a deterministic clock."""

    def __init__(self, **overrides):
        self.config = AppConfig(**overrides)
        self.mouse = FakeMouse()
        self.controller = MouseController(self.config, SafeGuard(), mouse_api=self.mouse)
        self.pipeline = GesturePipeline(self.config, self.controller, SCREEN)
        self.t = 10.0

    def frame(self, hand: HandObservation | None):
        self.t += DT
        return self.pipeline.step([hand] if hand is not None else [], self.t, self.t)

    def hold(self, hand, frames):
        outcome = None
        for _ in range(frames):
            outcome = self.frame(hand)
        return outcome

    def events(self, name):
        return [e for e in self.mouse.events if e[0] == name]


def test_pointing_moves_cursor_to_mapped_position():
    rig = Rig()
    rig.hold(pointing_hand(), 4)
    moves = rig.events("move")
    assert moves, "a confirmed POINT gesture should move the cursor"
    _, x, y = moves[-1]
    # Index tip is at (0.40, 0.10) in the synthetic hand; margin 0.08 -> usable 0.84.
    assert x == pytest.approx(2 + ((0.40 - 0.08) / 0.84) * (SCREEN[0] - 5), abs=3)
    assert y == pytest.approx(2 + ((0.10 - 0.08) / 0.84) * (SCREEN[1] - 5), abs=3)


def test_hand_at_edge_never_lands_on_a_failsafe_corner_pixel():
    corners = {(0, 0), (SCREEN[0] - 1, 0), (0, SCREEN[1] - 1), (SCREEN[0] - 1, SCREEN[1] - 1)}
    rig = Rig(active_margin=0.30)
    rig.hold(translate(pointing_hand(), -0.34, -0.10), 5)   # fingertip pinned to top-left
    rig.hold(translate(pointing_hand(), 0.55, 0.68), 40)     # fingertip pinned to bottom-right
    visited = {(x, y) for _, x, y in rig.events("move")}
    assert (2, 2) in visited
    assert (SCREEN[0] - 3, SCREEN[1] - 3) in visited
    assert not visited & corners


def test_without_inset_hand_at_edge_does_land_on_the_corner_pixel():
    # Documents the bug the inset fixes (PyAutoGUI would raise FailSafeException here).
    rig = Rig(active_margin=0.30, screen_edge_inset_px=0)
    rig.hold(translate(pointing_hand(), -0.34, -0.10), 5)
    assert ("move", 0, 0) in rig.mouse.events


def test_quick_pinch_and_release_is_one_left_click():
    rig = Rig()
    rig.hold(pointing_hand(), 4)
    rig.hold(pinch_hand(), 3)
    rig.hold(pointing_hand(), 4)
    assert rig.events("click") == [("click", "left")]
    assert not rig.events("down")


def test_held_pinch_drags_and_single_dropped_frame_does_not_release_it():
    rig = Rig()
    rig.hold(pointing_hand(), 4)
    rig.hold(pinch_hand(), 20)  # ~0.67 s > drag_hold_s
    assert rig.controller.dragging
    rig.frame(None)  # one missed detection is tolerated
    assert rig.controller.dragging
    assert not rig.events("up")


def test_sustained_tracking_loss_releases_drag():
    rig = Rig()
    rig.hold(pointing_hand(), 4)
    rig.hold(pinch_hand(), 20)
    assert rig.controller.dragging
    rig.hold(None, 2)
    assert not rig.controller.dragging
    assert rig.events("up") == [("up", "left")]


def test_one_ambiguous_frame_neither_clicks_nor_drops_the_active_gesture():
    rig = Rig()
    rig.hold(pointing_hand(), 4)
    broken = HandObservation(tuple([(0.5, 0.5, 0.0)] * 20))  # malformed -> UNKNOWN
    outcome = rig.frame(broken)
    assert outcome.raw_gesture == Gesture.UNKNOWN
    assert not outcome.dispatched
    assert rig.pipeline.current_gesture == Gesture.POINT
    assert not rig.events("click")


def test_two_finger_hand_scrolls_continuously_while_offset_and_stops_back_at_neutral():
    rig = Rig()
    rig.controller.raw_wheel_units = True
    rig.hold(pointing_hand(), 4)
    base = two_finger_hand()
    rig.hold(base, 6)
    assert not rig.events("scroll")                       # resting at neutral: nothing
    for step in range(1, 7):                               # ease the hand down ~0.12 of the frame
        rig.frame(translate(base, 0.0, 0.02 * step))
    rig.hold(translate(base, 0.0, 0.12), 20)               # ...and hold it there
    during = rig.events("scroll")
    assert len(during) >= 8, f"held offset should keep scrolling, got {len(during)} events"
    assert all(e[1] < 0 for e in during), "hand below start scrolls down"
    for step in range(5, -1, -1):                          # return to neutral
        rig.frame(translate(base, 0.0, 0.02 * step))
    rig.hold(base, 10)
    settled = len(rig.events("scroll"))
    rig.hold(base, 20)
    assert len(rig.events("scroll")) == settled, "must stop once the hand is back at neutral"
    assert all(e[1] < 0 for e in rig.events("scroll")), "return motion must not scroll upward"
    assert not rig.events("click"), "scrolling must not also right-click"


def test_transition_out_of_two_fingers_does_not_scroll_from_the_new_pose():
    """A stale confirmed TWO_FINGERS state must not scroll on a raw POINT frame."""
    rig = Rig()
    rig.controller.raw_wheel_units = True
    base = two_finger_hand()
    rig.hold(base, 6)
    before = len(rig.events("scroll"))

    # One frame of POINT is not enough to change temporal consensus from TWO_FINGERS,
    # but its fingertip is far below the scroll baseline. It must not become scroll input.
    transition = translate(pointing_hand(), 0.0, 0.18)
    outcome = rig.frame(transition)
    assert outcome.raw_gesture == Gesture.POINT
    assert outcome.gesture == Gesture.TWO_FINGERS
    assert len(rig.events("scroll")) == before, "transition pose must not be interpreted as scroll motion"


def test_controller_ignores_scroll_coordinate_when_raw_pose_is_not_two_fingers():
    rig = Rig()
    rig.controller.raw_wheel_units = True
    rig.hold(two_finger_hand(), 6)
    before = len(rig.events("scroll"))
    # Force a one-frame raw transition while the confirmed gesture remains TWO_FINGERS.
    rig.controller.update(
        Gesture.TWO_FINGERS,
        (400.0, 900.0),
        SCREEN,
        rig.t + DT,
        raw_gesture=Gesture.POINT,
        scroll_y=900.0,
    )
    assert len(rig.events("scroll")) == before


def test_flicking_down_and_back_repeatedly_scrolls_every_time():
    # End-to-end version of the "only 1 in 10 strokes registered" failure of the old design.
    rig = Rig()
    rig.controller.raw_wheel_units = True
    rig.hold(pointing_hand(), 4)
    base = two_finger_hand()
    rig.hold(base, 6)
    totals = []
    for _ in range(6):
        before = len(rig.events("scroll"))
        for step in range(1, 9):
            rig.frame(translate(base, 0.0, 0.02 * step))
        for step in range(7, -1, -1):
            rig.frame(translate(base, 0.0, 0.02 * step))
        totals.append(len(rig.events("scroll")) - before)
    assert all(n >= 1 for n in totals), totals


def test_fist_is_idle_and_cursor_does_not_follow_the_curling_finger():
    rig = Rig()
    rig.hold(pointing_hand(), 4)
    before = list(rig.mouse.events)
    rig.hold(fist_hand(), 10)
    assert rig.mouse.events == before


def test_scroll_anchor_uses_palm_center_not_fingertip_position():
    hand = two_finger_hand()
    moved_tip = list(hand.landmarks)
    moved_tip[8] = (moved_tip[8][0], moved_tip[8][1] + 0.06, moved_tip[8][2])
    moved_tip_hand = HandObservation(tuple(moved_tip))
    assert GesturePipeline._scroll_anchor_y(hand) == pytest.approx(
        GesturePipeline._scroll_anchor_y(moved_tip_hand)
    )


def test_cursor_stays_put_while_pose_changes_from_point_to_pinch():
    # Regression: the confirmed gesture lags the hand by a frame, and the fingertip
    # moves as the fingers close. The pointer must not follow it before the click.
    rig = Rig()
    rig.hold(pointing_hand(), 4)
    resting = rig.events("move")[-1]
    rig.hold(pinch_hand(), 3)
    rig.hold(pointing_hand(), 4)
    clicked_at = [e for e in rig.mouse.events if e[0] in ("move", "click")]
    click_index = next(i for i, e in enumerate(clicked_at) if e[0] == "click")
    last_move_before_click = next(e for e in reversed(clicked_at[:click_index]) if e[0] == "move")
    assert last_move_before_click == resting
