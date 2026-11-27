from nomouse.safety import WindowBounds, WindowSafetyGuard


def test_window_bounds_contains_inner_and_padded_edges():
    bounds = WindowBounds(100, 100, 300, 200)
    assert bounds.contains(200, 150)
    assert bounds.contains(95, 150, padding=8)
    assert not bounds.contains(90, 150, padding=8)
    assert not bounds.contains(500, 500, padding=8)


def test_safety_guard_can_use_embedded_preview_bounds():
    preview = WindowBounds(200, 150, 500, 300)
    guard = WindowSafetyGuard("embedded preview", bounds_provider=lambda: preview)
    assert not guard.allows_action(400, 300)
    assert "blocked" in guard.last_reason.lower()
    assert guard.allows_action(100, 100)


def test_missing_embedded_preview_bounds_fails_closed():
    guard = WindowSafetyGuard("embedded preview", bounds_provider=lambda: None)
    assert not guard.allows_action(100, 100)
    assert "unavailable" in guard.last_reason.lower()
