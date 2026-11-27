from nomouse.safety import WindowBounds


def test_window_bounds_contains_inner_and_padded_edges():
    bounds = WindowBounds(100, 100, 300, 200)
    assert bounds.contains(200, 150)
    assert bounds.contains(95, 150, padding=8)
    assert not bounds.contains(90, 150, padding=8)
    assert not bounds.contains(500, 500, padding=8)
