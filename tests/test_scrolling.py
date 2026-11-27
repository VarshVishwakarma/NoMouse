import random

import pytest

from nomouse.filters import OneEuroFilter
from nomouse.scrolling import WHEEL_DELTA, RateScroller

DT = 1 / 30


def run(scroller, offsets, base=500.0, start=0.0):
    """Feed hand heights (base + offset) at 30 fps; return the list of emitted deltas."""
    scroller.reset(base, start)
    out, t = [], start
    for off in offsets:
        t += DT
        out.append(scroller.update(base + off, t))
    return out


def test_resting_hand_never_scrolls_even_with_jitter():
    rng = random.Random(7)
    filt = OneEuroFilter(min_cutoff=3.0, beta=0.006)  # same smoother the app applies
    scroller = RateScroller()
    scroller.reset(500.0, 0.0)
    t, sent = 0.0, 0
    for _ in range(30 * 20):  # 20 seconds of holding still with 3 px of tracking noise
        t += DT
        sent += abs(scroller.update(filt(500.0 + rng.gauss(0, 3.0), t), t))
    assert sent == 0


def test_hand_below_neutral_scrolls_down_and_above_scrolls_up():
    down = run(RateScroller(), [120] * 30)
    up = run(RateScroller(), [-120] * 30)
    assert sum(down) < 0 and all(d <= 0 for d in down)
    assert sum(up) > 0 and all(d >= 0 for d in up)


def test_invert_flips_direction():
    assert sum(run(RateScroller(invert=True), [120] * 30)) > 0


def test_farther_from_neutral_scrolls_faster():
    totals = [abs(sum(run(RateScroller(), [off] * 30))) for off in (40, 80, 160, 300)]
    assert totals == sorted(totals) and len(set(totals)) == 4


def test_speed_is_capped_at_max_speed():
    one_second = abs(sum(run(RateScroller(max_speed=10.0), [900] * 30)))
    assert one_second <= 10.0 * WHEEL_DELTA * 1.05
    assert one_second >= 10.0 * WHEEL_DELTA * 0.85


def test_scrolling_is_actually_substantial():
    # Regression for "very slow": the old design sent 3 raw units (2.5% of a notch) per stroke.
    one_second = abs(sum(run(RateScroller(), [100] * 30)))
    assert one_second >= 5 * WHEEL_DELTA  # at least ~5 whole notches/second at a moderate offset


def test_returning_to_neutral_stops_without_reverse_scroll():
    deltas = run(RateScroller(), [120] * 20 + [60, 30, 10, 0] + [0] * 20)
    assert all(d <= 0 for d in deltas), "return motion must never scroll the opposite way"
    assert all(d == 0 for d in deltas[-20:]), "scrolling must stop once the hand is back at neutral"


def test_flick_and_return_rhythm_scrolls_every_time():
    # Regression for "not working properly": the old stroke detector needed a ~200+ ms pause
    # between strokes; without one only 1 of 10 strokes registered.
    scroller = RateScroller()
    scroller.reset(500.0, 0.0)
    t, per_stroke = 0.0, []
    for _ in range(10):
        total = 0
        for off in [i * 12 for i in range(1, 11)] + [120 - i * 12 for i in range(1, 11)]:  # no pause at all
            t += DT
            total += scroller.update(500.0 + off, t)
        per_stroke.append(total)
    assert all(total < 0 for total in per_stroke), per_stroke


def test_direction_reversal_through_neutral_has_no_leftover_from_other_direction():
    deltas = run(RateScroller(), [120] * 10 + [-120] * 10)
    first, second = deltas[:10], deltas[10:]
    assert sum(first) < 0 and sum(second) > 0
    assert all(d <= 0 for d in first) and all(d >= 0 for d in second)


def test_neutral_point_follows_slow_drift_but_not_deliberate_movement():
    # A hand sinking 30 px over 10 s (3 px/s) should be absorbed; moving 30 px in 0.3 s should not.
    drift = run(RateScroller(), [i * 0.1 for i in range(300)])
    assert sum(abs(d) for d in drift) == 0
    deliberate = run(RateScroller(), [0] * 5 + [i * 3 for i in range(1, 12)] + [33] * 20)
    assert sum(deliberate) < 0


def test_emits_only_multiples_of_wheel_step_and_conserves_distance():
    scroller = RateScroller(wheel_step=40)
    deltas = run(scroller, [100] * 60)
    assert all(d % 40 == 0 for d in deltas)
    expected = -scroller.speed(100) * WHEEL_DELTA * (59 * DT)  # first frame only sets the baseline
    assert sum(deltas) == pytest.approx(expected, abs=40 + 1)


def test_stalled_frame_does_not_cause_a_burst():
    scroller = RateScroller()
    scroller.reset(500.0, 0.0)
    scroller.update(620.0, 0.033)
    burst = abs(scroller.update(620.0, 5.0))  # 5 s later (e.g. the app froze)
    assert burst <= 25.0 * WHEEL_DELTA * 0.1 + 40


def test_reset_clears_state():
    scroller = RateScroller()
    run(scroller, [200] * 5)
    scroller.reset()
    assert scroller.update(900.0, 10.0) == 0  # first sample after reset only sets the neutral point
    assert scroller.anchor_y == 900.0


def test_wheel_step_is_clamped_to_one_notch():
    assert RateScroller(wheel_step=9999).wheel_step == WHEEL_DELTA
