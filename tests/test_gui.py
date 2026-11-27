import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json

import pytest
from PySide6.QtWidgets import QApplication

from nomouse.config import AppConfig
from nomouse.gui import NoMouseWindow, OnboardingWizard, main
from nomouse.gui_worker import BoundsSnapshot, PerformanceReport
from nomouse.safety import WindowBounds


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_desktop_window_builds_all_integrated_sections(qt_app, tmp_path):
    window = NoMouseWindow(AppConfig(), tmp_path / "settings.json")
    assert window.pages.count() == len(NoMouseWindow.NAV_ITEMS) == 5
    assert window.start_button.text() == "Start control"
    assert window.stop_button.text() == "Stop"
    assert not window.stop_button.isEnabled()
    window.close()


def test_settings_and_guided_calibration_persist_runtime_values(qt_app, tmp_path):
    config_path = tmp_path / "settings.json"
    window = NoMouseWindow(AppConfig(), config_path)
    window.navigate(2)
    window.cursor_smoothing.setValue(0.65)
    window.scroll_speed.setValue(32.0)
    window.camera_fps.setValue(24)
    window.gesture_toggles["scroll_enabled"].setChecked(False)
    window.apply_settings()
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["cursor_smoothing"] == pytest.approx(0.65)
    assert saved["scroll_max_speed"] == pytest.approx(32.0)
    assert saved["camera_fps"] == 24
    assert saved["scroll_enabled"] is False

    window.navigate(1)
    window.calibration_margin.setValue(0.12)
    window.calibration_smoothing.setValue(0.40)
    window.apply_settings()
    persisted = json.loads(config_path.read_text(encoding="utf-8"))
    assert persisted["active_margin"] == pytest.approx(0.12)
    assert persisted["cursor_smoothing"] == pytest.approx(0.40)
    assert window.active_margin.value() == pytest.approx(0.12)
    window.close()


def test_onboarding_covers_setup_and_safety(qt_app):
    wizard = OnboardingWizard()
    assert wizard.pageIds()
    assert len(wizard.pageIds()) == 6
    assert "safety" in wizard.page(wizard.pageIds()[-1]).title().lower()
    wizard.close()


def test_bounds_snapshot_is_safe_for_cross_thread_preview_updates():
    bounds = BoundsSnapshot()
    assert bounds.get() is None
    bounds.set(WindowBounds(10, 20, 320, 240))
    assert bounds.get() == WindowBounds(10, 20, 320, 240)


def test_diagnostics_report_contains_only_aggregate_fields():
    report = PerformanceReport(frames=30, frame_p95_ms=24.0, tracking_interruptions=2)
    assert report.frames == 30
    assert report.frame_p95_ms == 24.0
    assert not hasattr(report, "landmarks")


def test_desktop_entry_point_supports_version_flag():
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
