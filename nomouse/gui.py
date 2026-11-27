"""Qt desktop application for NoMouse."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from . import __version__
from .config import AppConfig, default_config_path, load_config, save_config
from .gui_worker import BoundsSnapshot, CameraWorker, PerformanceReport
from .safety import WindowBounds

_STYLE = """
QMainWindow, QWidget#root { background: #10131a; color: #edf1f7; }
QWidget { color: #edf1f7; font-family: "Segoe UI"; font-size: 10pt; }
QFrame#sidebar { background: #171b24; border-right: 1px solid #252b37; }
QFrame#card { background: #191e29; border: 1px solid #293142; border-radius: 12px; }
QLabel#muted { color: #99a4b5; }
QLabel#eyebrow { color: #8d9bb2; font-size: 9pt; font-weight: 600; }
QLabel#metric { color: #f5f7fb; font-size: 22pt; font-weight: 700; }
QLabel#title { font-size: 20pt; font-weight: 700; }
QLabel#section { font-size: 14pt; font-weight: 650; }
QPushButton { background: #222938; border: 1px solid #30394b; border-radius: 8px; padding: 9px 14px; }
QPushButton:hover { background: #2b3547; }
QPushButton:disabled { color: #677286; background: #191e29; }
QPushButton#primary { color: #07130f; background: #72e0b0; border: 0; font-weight: 700; }
QPushButton#primary:hover { background: #8cebc0; }
QPushButton#danger { color: #ffd5d8; background: #45252d; border: 1px solid #68313b; }
QPushButton#nav { text-align: left; padding: 12px; background: transparent; border: 0; color: #b6c0cf; }
QPushButton#nav:checked { color: #82e6ba; background: #222d32; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
  background: #10151e; border: 1px solid #30394b; border-radius: 6px; padding: 7px;
}
QComboBox QAbstractItemView { background: #191e29; selection-background-color: #315a4c; }
QSlider::groove:horizontal { height: 5px; background: #30394b; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #72e0b0; }
QSlider::handle:horizontal { background: #d7ffe9; width: 14px; margin: -5px 0; border-radius: 7px; }
QScrollArea { border: 0; background: transparent; }
QWizard { background: #10131a; }
"""


class OnboardingWizard(QWizard):
    """Short first-run guide; no setup step requires source-code knowledge."""

    STEPS = (
        ("Set up your camera", "Place the webcam at eye level, keep your hand visible, and use steady front lighting."),
        ("Find a comfortable range", "Keep your hand near the center of the preview with your palm facing the camera."),
        (
            "Move the pointer",
            "Extend your index finger and move your hand slowly; "
            "cursor sensitivity is adjustable in Settings.",
        ),
        ("Click and drag", "Briefly pinch thumb to index to click. Hold the pinch to drag, then separate to release."),
        (
            "Scroll and pause",
            "Raise index and middle fingers to scroll. Press Pause at any time; "
            "Stop releases controls and closes the camera.",
        ),
        (
            "Use the safety stop",
            "Keep a physical mouse nearby. Its corner fail-safe remains enabled; "
            "NoMouse processes frames locally.",
        ),
    )

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to NoMouse")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        for title, text in self.STEPS:
            page = QWizardPage()
            page.setTitle(title)
            label = QLabel(text)
            label.setWordWrap(True)
            label.setMinimumWidth(420)
            layout = QVBoxLayout(page)
            layout.addWidget(label)
            self.addPage(page)


class NoMouseWindow(QMainWindow):
    """Dashboard and settings UI; the camera and control loop live on a worker thread."""

    NAV_ITEMS = ("Dashboard", "Calibration", "Settings", "Guide", "Diagnostics")

    def __init__(self, config: AppConfig, config_path: Path):
        super().__init__()
        self.config = config
        self.config_path = config_path
        self.worker: CameraWorker | None = None
        self.bounds = BoundsSnapshot()
        self.report = PerformanceReport()
        self._image: QImage | None = None
        self._page_index = 0
        self.setWindowTitle(f"NoMouse · {__version__}")
        self.setMinimumSize(1040, 700)
        self.resize(1240, 820)

        root = QWidget()
        root.setObjectName("root")
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setCentralWidget(root)
        outer.addWidget(self._build_sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 22, 28, 20)
        content_layout.setSpacing(16)
        outer.addWidget(content, 1)

        header = QHBoxLayout()
        self.page_title = QLabel("Dashboard")
        self.page_title.setObjectName("title")
        header.addWidget(self.page_title)
        header.addStretch(1)
        self.status_label = QLabel("Ready · camera not connected")
        self.status_label.setObjectName("muted")
        header.addWidget(self.status_label)
        self.start_button = QPushButton("Start control")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.start_control)
        header.addWidget(self.start_button)
        self.pause_button = QPushButton("Pause")
        self.pause_button.setEnabled(False)
        self.pause_button.clicked.connect(self.toggle_pause)
        header.addWidget(self.pause_button)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("danger")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_control)
        header.addWidget(self.stop_button)
        content_layout.addLayout(header)

        self.pages = QStackedWidget()
        content_layout.addWidget(self.pages, 1)
        self._build_dashboard()
        self._build_calibration()
        self._build_settings()
        self._build_guide()
        self._build_diagnostics()

        self._bounds_timer = QTimer(self)
        self._bounds_timer.timeout.connect(self._update_preview_bounds)
        self._bounds_timer.start(150)
        self._worker_timer = QTimer(self)
        self._worker_timer.timeout.connect(self._check_worker)
        self._worker_timer.start(200)
        self.setStyleSheet(_STYLE)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(205)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 20, 16, 16)
        brand = QLabel("NoMouse")
        brand.setStyleSheet("font-size: 18pt; font-weight: 750; color: #82e6ba;")
        layout.addWidget(brand)
        tagline = QLabel("TOUCHLESS CONTROL")
        tagline.setObjectName("eyebrow")
        layout.addWidget(tagline)
        layout.addSpacing(24)
        self.nav_buttons: list[QPushButton] = []
        for index, name in enumerate(self.NAV_ITEMS):
            button = QPushButton(name)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, i=index: self.navigate(i))
            self.nav_buttons.append(button)
            layout.addWidget(button)
        self.nav_buttons[0].setChecked(True)
        layout.addStretch(1)
        privacy = QLabel("LOCAL PROCESSING\nCamera frames stay on this device.")
        privacy.setObjectName("muted")
        privacy.setWordWrap(True)
        layout.addWidget(privacy)
        version = QLabel(f"Version {__version__}")
        version.setObjectName("muted")
        layout.addWidget(version)
        return sidebar

    def _page(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("section")
        hint = QLabel(subtitle)
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(hint)
        self.pages.addWidget(page)
        return page, layout

    def _build_dashboard(self) -> None:
        page, layout = self._page(
            "Hands-free control",
            "Start a private, local camera session. Keep a physical mouse nearby while learning the gestures.",
        )
        metrics = QHBoxLayout()
        self.gesture_value = self._metric_label("SEARCHING")
        self.fps_value = self._metric_label("—")
        self.latency_value = self._metric_label("—")
        self.tracking_value = self._metric_label("Idle")
        for title, value in (
            ("Gesture", self.gesture_value),
            ("Session rate", self.fps_value),
            ("Processing p95", self.latency_value),
            ("Tracking", self.tracking_value),
        ):
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 12, 16, 12)
            eyebrow = QLabel(title.upper())
            eyebrow.setObjectName("eyebrow")
            card_layout.addWidget(eyebrow)
            card_layout.addWidget(value)
            metrics.addWidget(card, 1)
        layout.addLayout(metrics)

        preview_card = QFrame()
        preview_card.setObjectName("card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_heading = QHBoxLayout()
        preview_heading.addWidget(QLabel("LIVE CAMERA"))
        preview_heading.addStretch(1)
        self.camera_badge = QLabel("Disconnected")
        self.camera_badge.setObjectName("muted")
        preview_heading.addWidget(self.camera_badge)
        preview_layout.addLayout(preview_heading)
        self.preview = QLabel("Camera preview appears here when you start NoMouse")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(480, 330)
        self.preview.setStyleSheet("background: #090c11; border-radius: 8px; color: #8d9bb2;")
        preview_layout.addWidget(self.preview, 1)
        layout.addWidget(preview_card, 1)

    @staticmethod
    def _metric_label(value: str) -> QLabel:
        label = QLabel(value)
        label.setObjectName("metric")
        return label

    def _build_calibration(self) -> None:
        page, layout = self._page(
            "Guided calibration",
            "Use the live preview, then tune the active camera region and movement feel. "
            "Changes save to your local profile.",
        )
        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        form.setContentsMargins(20, 18, 20, 18)
        self.calibration_margin = QDoubleSpinBox()
        self.calibration_margin.setRange(0.0, 0.35)
        self.calibration_margin.setSingleStep(0.01)
        self.calibration_margin.setSuffix(" active margin")
        self.calibration_smoothing = QDoubleSpinBox()
        self.calibration_smoothing.setRange(0.0, 1.0)
        self.calibration_smoothing.setSingleStep(0.05)
        self.calibration_smoothing.setSuffix(" smoothing")
        self.calibration_scroll_speed = QDoubleSpinBox()
        self.calibration_scroll_speed.setRange(1.0, 80.0)
        self.calibration_scroll_speed.setSingleStep(1.0)
        form.addRow("Cursor boundary", self.calibration_margin)
        form.addRow("Cursor stability", self.calibration_smoothing)
        form.addRow("Maximum scroll rate", self.calibration_scroll_speed)
        layout.addWidget(card)

        steps = QLabel(
            "1. Center your hand in the preview and keep the palm facing the camera.\n"
            "2. Extend your index finger and move to each comfortable screen edge.\n"
            "3. Adjust the boundary and smoothing until movement feels controllable.\n"
            "4. Raise two fingers, settle at neutral, then press Recenter while the pose is active.\n"
            "5. Try a short pinch and scroll over a harmless window before normal use."
        )
        steps.setWordWrap(True)
        steps.setObjectName("muted")
        layout.addWidget(steps)
        buttons = QHBoxLayout()
        self.recenter_button = QPushButton("Recenter scroll neutral")
        self.recenter_button.setEnabled(False)
        self.recenter_button.clicked.connect(self.recenter_scroll)
        buttons.addWidget(self.recenter_button)
        save = QPushButton("Save calibration")
        save.setObjectName("primary")
        save.clicked.connect(self.apply_settings)
        buttons.addWidget(save)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        layout.addStretch(1)

    def _build_settings(self) -> None:
        page, layout = self._page(
            "Control settings",
            "Settings are validated and saved locally. Stop the live session before applying changes.",
        )
        area = QScrollArea()
        area.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(18, 12, 18, 12)
        form.setSpacing(12)
        self.camera_index = QComboBox()
        for index in range(17):
            self.camera_index.addItem(f"Camera {index}", index)
        form.addRow("Camera device index", self.camera_index)
        self.resolution = QComboBox()
        for resolution in ("640 × 480", "1280 × 720", "1920 × 1080"):
            self.resolution.addItem(resolution)
        form.addRow("Capture resolution", self.resolution)
        self.camera_fps = self._integer(10, 60)
        form.addRow("Requested capture FPS", self.camera_fps)
        self.cursor_smoothing = self._double(0.0, 1.0, 0.05)
        form.addRow("Cursor smoothing", self.cursor_smoothing)
        self.active_margin = self._double(0.0, 0.35, 0.01)
        form.addRow("Active-region margin", self.active_margin)
        self.pinch_threshold = self._double(0.20, 0.50, 0.01)
        form.addRow("Pinch sensitivity threshold", self.pinch_threshold)
        self.click_frames = self._integer(1, 8)
        form.addRow("Click confirmation frames", self.click_frames)
        self.drag_hold = self._double(0.25, 1.25, 0.05)
        form.addRow("Drag activation (seconds)", self.drag_hold)
        self.scroll_speed = self._double(1.0, 80.0, 1.0)
        form.addRow("Maximum scroll rate", self.scroll_speed)
        self.scroll_deadzone = self._double(5.0, 150.0, 1.0)
        form.addRow("Scroll deadzone (pixels)", self.scroll_deadzone)
        self.scroll_wheel_step = self._integer(10, 120)
        form.addRow("Scroll event step", self.scroll_wheel_step)
        self.tracking_confidence = self._double(0.10, 0.99, 0.05)
        form.addRow("Tracking confidence", self.tracking_confidence)

        self.scroll_invert = QPushButton("Scroll direction: natural")
        self.scroll_invert.setCheckable(True)
        self.scroll_invert.toggled.connect(
            lambda checked: self.scroll_invert.setText(
                "Scroll direction: inverted" if checked else "Scroll direction: natural"
            )
        )
        form.addRow("Direction", self.scroll_invert)
        self.gesture_toggles: dict[str, QPushButton] = {}
        for key, label in (
            ("left_click_enabled", "Pinch click and drag"),
            ("right_click_enabled", "Two-finger tap right-click"),
            ("scroll_enabled", "Two-finger scrolling"),
            ("browser_back_enabled", "Four-finger browser back"),
            ("show_landmarks", "Show hand landmarks in preview"),
            ("safety_guard_enabled", "Block actions over preview"),
        ):
            button = QPushButton(label)
            button.setCheckable(True)
            form.addRow(label, button)
            self.gesture_toggles[key] = button
        area.setWidget(body)
        layout.addWidget(area, 1)
        footer = QHBoxLayout()
        apply_button = QPushButton("Apply and save")
        apply_button.setObjectName("primary")
        apply_button.clicked.connect(self.apply_settings)
        defaults_button = QPushButton("Restore defaults")
        defaults_button.clicked.connect(self.restore_defaults)
        footer.addWidget(apply_button)
        footer.addWidget(defaults_button)
        footer.addStretch(1)
        layout.addLayout(footer)
        self._load_settings_widgets()

    @staticmethod
    def _double(low: float, high: float, step: float) -> QDoubleSpinBox:
        control = QDoubleSpinBox()
        control.setRange(low, high)
        control.setSingleStep(step)
        control.setDecimals(2)
        return control

    @staticmethod
    def _integer(low: int, high: int) -> QSpinBox:
        control = QSpinBox()
        control.setRange(low, high)
        return control

    def _load_settings_widgets(self) -> None:
        c = self.config
        self.camera_index.setCurrentIndex(max(0, self.camera_index.findData(c.camera_index)))
        resolution = f"{c.camera_width} × {c.camera_height}"
        index = self.resolution.findText(resolution)
        self.resolution.setCurrentIndex(max(0, index))
        self.camera_fps.setValue(c.camera_fps)
        self.cursor_smoothing.setValue(c.cursor_smoothing)
        self.active_margin.setValue(c.active_margin)
        self.pinch_threshold.setValue(c.pinch_threshold)
        self.click_frames.setValue(c.click_confirm_frames)
        self.drag_hold.setValue(c.drag_hold_s)
        self.scroll_speed.setValue(c.scroll_max_speed)
        self.scroll_deadzone.setValue(c.scroll_deadzone_px)
        self.scroll_wheel_step.setValue(c.scroll_wheel_step)
        self.tracking_confidence.setValue(c.min_tracking_confidence)
        self.scroll_invert.setChecked(c.scroll_invert)
        for key, button in self.gesture_toggles.items():
            button.setChecked(bool(getattr(c, key)))
        self.calibration_margin.setValue(c.active_margin)
        self.calibration_smoothing.setValue(c.cursor_smoothing)
        self.calibration_scroll_speed.setValue(c.scroll_max_speed)

    def apply_settings(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "Stop the live session", "Stop NoMouse before applying settings.")
            return
        c = self.config
        c.camera_index = int(self.camera_index.currentData())
        width, height = self.resolution.currentText().replace(" ", "").split("×")
        c.camera_width, c.camera_height = int(width), int(height)
        c.camera_fps = self.camera_fps.value()
        c.cursor_smoothing = self.cursor_smoothing.value()
        c.active_margin = self.active_margin.value()
        c.pinch_threshold = self.pinch_threshold.value()
        c.click_confirm_frames = self.click_frames.value()
        c.drag_hold_s = self.drag_hold.value()
        c.scroll_max_speed = self.scroll_speed.value()
        c.scroll_deadzone_px = self.scroll_deadzone.value()
        c.scroll_wheel_step = self.scroll_wheel_step.value()
        c.min_tracking_confidence = self.tracking_confidence.value()
        c.scroll_invert = self.scroll_invert.isChecked()
        for key, button in self.gesture_toggles.items():
            setattr(c, key, button.isChecked())
        if self._page_index == 1:
            c.active_margin = self.calibration_margin.value()
            c.cursor_smoothing = self.calibration_smoothing.value()
            c.scroll_max_speed = self.calibration_scroll_speed.value()
        save_config(c, self.config_path)
        self._load_settings_widgets()
        self.status_label.setText("Settings saved locally")

    def restore_defaults(self) -> None:
        self.config = AppConfig()
        self._load_settings_widgets()
        self.apply_settings()

    def _build_guide(self) -> None:
        page, layout = self._page(
            "Gesture guide",
            "Begin with the primary gestures. Work over a harmless window until control feels predictable.",
        )
        guide = (
            ("POINT", "Extend index finger to move the pointer."),
            ("PINCH", "Touch thumb and index briefly to click; hold to drag, release to drop."),
            ("TWO FINGERS", "Index and middle fingers scroll relative to the gesture start; a still tap right-clicks."),
            ("FOUR FINGERS", "Optional browser-back shortcut. Disable it in Settings if it is not comfortable."),
            ("OPEN PALM / FIST", "Rest pose. Use Pause to stop input immediately."),
        )
        for gesture, instruction in guide:
            card = QFrame()
            card.setObjectName("card")
            row = QHBoxLayout(card)
            name = QLabel(gesture)
            name.setObjectName("eyebrow")
            name.setMinimumWidth(155)
            detail = QLabel(instruction)
            detail.setWordWrap(True)
            row.addWidget(name)
            row.addWidget(detail, 1)
            layout.addWidget(card)
        layout.addStretch(1)

    def _build_diagnostics(self) -> None:
        page, layout = self._page(
            "Session diagnostics",
            "Metrics describe software processing only. No frames, hand landmarks, "
            "or personal identifiers are included in exported reports.",
        )
        self.diagnostics_label = QLabel("Start a session to collect performance measurements.")
        self.diagnostics_label.setWordWrap(True)
        self.diagnostics_label.setObjectName("muted")
        layout.addWidget(self.diagnostics_label)
        export = QPushButton("Export session report")
        export.clicked.connect(self.export_report)
        layout.addWidget(export, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)

    def navigate(self, index: int) -> None:
        self._page_index = index
        self.pages.setCurrentIndex(index)
        self.page_title.setText(self.NAV_ITEMS[index])
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)

    def start_control(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self.apply_settings()
        self.worker = CameraWorker(self.config, self.bounds)
        self.worker.frame_ready.connect(self._show_frame)
        self.worker.status_changed.connect(self._set_status)
        self.worker.metrics_updated.connect(self._update_metrics)
        self.worker.failure.connect(self._show_failure)
        self.worker.request_pause(False)
        self.worker.start()
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.recenter_button.setEnabled(True)
        self.camera_badge.setText(f"Connecting · camera {self.config.camera_index}")
        self.status_label.setText("Starting camera and hand tracker…")

    def toggle_pause(self) -> None:
        if self.worker is None:
            return
        paused = self.pause_button.text() == "Pause"
        self.worker.request_pause(paused)
        self.pause_button.setText("Resume" if paused else "Pause")
        self.status_label.setText("Paused · input disabled" if paused else "Resuming control…")

    def stop_control(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_stop()
            self.status_label.setText("Stopping · releasing controls and camera…")
            self.stop_button.setEnabled(False)

    def recenter_scroll(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_scroll_recenter()
            self.status_label.setText("Hold two fingers steady to set scroll neutral")

    def _show_frame(self, image: QImage) -> None:
        self._image = image
        self._render_frame()

    def _render_frame(self) -> None:
        if self._image is None:
            return
        self.preview.setPixmap(
            QPixmap.fromImage(self._image).scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._render_frame()

    def _update_preview_bounds(self) -> None:
        point = self.preview.mapToGlobal(QPoint(0, 0))
        self.bounds.set(WindowBounds(point.x(), point.y(), self.preview.width(), self.preview.height()))

    def _set_status(self, status: str) -> None:
        self.status_label.setText(status)
        self.camera_badge.setText("Connected" if status.startswith("Live") else status)

    def _update_metrics(self, values: dict) -> None:
        self.gesture_value.setText(values["gesture"])
        self.fps_value.setText(f"{values['fps']:.1f}")
        self.latency_value.setText(f"{values['frame_p95_ms']:.1f} ms")
        self.tracking_value.setText("Hand detected" if values["detected"] else "Searching")
        self.report = PerformanceReport(**values)
        self.diagnostics_label.setText(
            f"Frames processed: {values['frames']}\n"
            f"Frame intervals > 33 ms: {values['slow_intervals']}\n"
            f"Tracking interruptions: {values['tracking_interruptions']}\n"
            f"Capture read: {values['capture_ms']:.2f} ms\n"
            f"MediaPipe inference: {values['inference_ms']:.2f} ms\n"
            f"Gesture + controller decision: {values['decision_ms']:.2f} ms\n"
            f"Frame processing p50 / p95: {values['frame_p50_ms']:.2f} / "
            f"{values['frame_p95_ms']:.2f} ms\n"
            "Frame processing includes software inference and conversion; excludes "
            "physical camera exposure and display scan-out."
        )

    def _show_failure(self, message: str) -> None:
        self.status_label.setText("Stopped · " + message)
        self.camera_badge.setText("Needs attention")
        QMessageBox.warning(self, "NoMouse session stopped", message)

    def _check_worker(self) -> None:
        if self.worker is None or self.worker.isRunning():
            return
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("Pause")
        self.stop_button.setEnabled(False)
        self.recenter_button.setEnabled(False)
        if self.status_label.text().startswith("Stopping"):
            self.status_label.setText("Stopped · controls released")
        if self._image is None:
            self.camera_badge.setText("Disconnected")

    def export_report(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self, "Export NoMouse diagnostics", "nomouse-session.json", "JSON files (*.json)"
        )
        if not target:
            return
        payload = {
            "nomouse_version": __version__,
            "platform": platform.platform(),
            "metrics": asdict(self.report),
            "settings": {
                "camera_resolution": [self.config.camera_width, self.config.camera_height],
                "cursor_smoothing": self.config.cursor_smoothing,
                "scroll_max_speed": self.config.scroll_max_speed,
            },
        }
        Path(target).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        self.status_label.setText(f"Diagnostics exported to {Path(target).name}")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.worker.request_stop()
            if not self.worker.wait(2500):
                QMessageBox.information(
                    self,
                    "Stopping safely",
                    "The camera is still shutting down. Wait for the session to stop, then close NoMouse.",
                )
                event.ignore()
                return
        event.accept()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nomouse", description="NoMouse touchless desktop control")
    parser.add_argument("--version", action="version", version=f"NoMouse {__version__}")
    parser.add_argument("--config", type=Path, default=None, help="settings JSON file")
    args = parser.parse_args(argv)
    path = args.config if args.config is not None else default_config_path()
    config = load_config(path)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("NoMouse")
    app.setOrganizationName("NoMouse")
    window = NoMouseWindow(config, path)
    window.show()
    if not config.onboarding_complete:
        QTimer.singleShot(250, lambda: _show_onboarding(window))
    return app.exec()


def _show_onboarding(window: NoMouseWindow) -> None:
    wizard = OnboardingWizard(window)
    if wizard.exec() == QWizard.DialogCode.Accepted:
        window.config.onboarding_complete = True
        save_config(window.config, window.config_path)


if __name__ == "__main__":
    raise SystemExit(main())
