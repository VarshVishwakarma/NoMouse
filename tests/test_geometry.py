import pytest

from nomouse.geometry import normalize_point, to_screen, to_screen_float

W, H = 1920, 1080


def test_center_of_camera_maps_to_center_of_screen():
    sx, sy = to_screen_float(0.5, 0.5, W, H, margin=0.08)
    assert sx == pytest.approx((W - 1) / 2)
    assert sy == pytest.approx((H - 1) / 2)


def test_points_outside_active_region_are_clamped():
    assert normalize_point(-1.0, 2.0, 0.1) == (0.0, 1.0)


def test_default_inset_reaches_exact_corner_pixels():
    assert to_screen(0.0, 0.0, W, H, margin=0.1) == (0, 0)
    assert to_screen(1.0, 1.0, W, H, margin=0.1) == (W - 1, H - 1)


def test_inset_keeps_pointer_off_failsafe_corner_pixels():
    assert to_screen(0.0, 0.0, W, H, margin=0.1, inset_px=2) == (2, 2)
    assert to_screen(1.0, 1.0, W, H, margin=0.1, inset_px=2) == (W - 3, H - 3)


def test_inset_preserves_center_and_scales_linearly():
    plain = to_screen_float(0.5, 0.5, W, H, margin=0.0)
    inset = to_screen_float(0.5, 0.5, W, H, margin=0.0, inset_px=10)
    assert inset == pytest.approx(plain)
    quarter = to_screen_float(0.25, 0.25, W, H, margin=0.0, inset_px=10)
    assert quarter[0] == pytest.approx(10 + 0.25 * (W - 1 - 20))


def test_oversized_inset_cannot_invert_the_mapping_on_tiny_screens():
    sx, sy = to_screen_float(1.0, 1.0, 10, 10, margin=0.0, inset_px=500)
    assert 0.0 <= sx <= 9.0 and 0.0 <= sy <= 9.0
