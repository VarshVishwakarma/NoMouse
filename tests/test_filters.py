from nomouse.filters import OneEuroFilter


def test_filter_initial_value_is_unchanged():
    filt = OneEuroFilter()
    assert filt(12.0, 1.0) == 12.0


def test_filter_output_is_finite_and_tracks_target():
    filt = OneEuroFilter()
    values = [filt(float(v), i / 30) for i, v in enumerate([0, 10, 20, 30, 40], start=1)]
    assert all(abs(v) < 1000 for v in values)
    assert values[-1] > values[0]
    assert values[-1] <= 40


def test_reset_reinitializes_filter():
    filt = OneEuroFilter()
    filt(1.0, 1.0)
    filt.reset()
    assert filt(99.0, 2.0) == 99.0


def test_adaptive_filter_responds_faster_to_fast_motion_than_fixed_cutoff():
    adaptive = OneEuroFilter(min_cutoff=1.6, beta=0.012)
    fixed = OneEuroFilter(min_cutoff=1.6, beta=0.0)
    samples = [0.0, 1.0, 2.0, 25.0, 60.0]
    adaptive_values = [adaptive(value, i / 30) for i, value in enumerate(samples, start=1)]
    fixed_values = [fixed(value, i / 30) for i, value in enumerate(samples, start=1)]
    assert adaptive_values[-1] > fixed_values[-1]
    assert adaptive_values[-1] <= samples[-1]


def test_one_euro_derivative_uses_previous_raw_sample_not_filtered_output():
    import math

    filt = OneEuroFilter(min_cutoff=1.0, beta=1.0, d_cutoff=1.0)
    filt(0.0, 0.0)

    dt = 1.0
    alpha_d = filt._alpha(1.0, dt)
    expected_edx_1 = alpha_d * 10.0
    expected_cutoff_1 = 1.0 + abs(expected_edx_1)
    alpha_x_1 = filt._alpha(expected_cutoff_1, dt)
    expected_1 = alpha_x_1 * 10.0
    assert math.isclose(filt(10.0, 1.0), expected_1, rel_tol=1e-9, abs_tol=1e-9)

    # The raw signal is now stationary. The second derivative is zero, even though
    # the filtered output has not yet caught up with the raw input.
    alpha_d_2 = filt._alpha(1.0, dt)
    expected_edx_2 = expected_edx_1 + alpha_d_2 * (0.0 - expected_edx_1)
    expected_cutoff_2 = 1.0 + abs(expected_edx_2)
    alpha_x_2 = filt._alpha(expected_cutoff_2, dt)
    expected_2 = expected_1 + alpha_x_2 * (10.0 - expected_1)
    assert math.isclose(filt(10.0, 2.0), expected_2, rel_tol=1e-9, abs_tol=1e-9)


def test_filter_handles_non_monotonic_timestamp_without_non_finite_output():
    filt = OneEuroFilter()
    vals = [filt(1.0, 1.0), filt(2.0, 0.5), filt(3.0, 0.4), filt(4.0, 1.1)]
    assert all(abs(value) < float('inf') for value in vals)
