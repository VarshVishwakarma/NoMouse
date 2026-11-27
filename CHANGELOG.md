# Changelog

## 3.0.0 — Desktop application

### Added
- Native Qt Widgets dashboard with an embedded camera preview, background camera/control worker, live gesture status, pause/stop, settings, onboarding, guided calibration, and aggregate-only diagnostic export.
- Local bundled MediaPipe Hand Landmarker task model, so inference remains offline after installation.
- Configurable pinch sensitivity and enable/disable controls for click, right-click, scroll, browser-back, landmarks, and preview safety.
- Camera index, resolution, and requested capture-FPS settings with range validation; actual capture rate remains device-dependent.
- Session FPS, capture/inference/decision timing, processing p50/p95, delayed-frame intervals, and tracking-interruption counters.
- PyInstaller Windows onedir build recipe, Windows build helper, package smoke-build workflow, and runtime dependency audit workflow.

### Changed
- The `nomouse` and `python main.py` launchers now open the desktop application. The original OpenCV loop remains available as `nomouse-cli`.
- Hand tracking migrated from the removed `mp.solutions` API to MediaPipe Tasks VIDEO mode. The official hand model is bundled; runtime use does not fetch models from the network.
- Scroll anchoring now follows the palm center rather than the index fingertip, reducing sensitivity to fingertip movement. The calibration page can recenter the neutral position during a two-finger pose.
- OS input failures fail closed. A potentially held left button is tracked before `mouseDown`; an uncertain failed release remains explicitly latched and blocks further control instead of being reported as released.
- Runtime dependencies move to MediaPipe 0.10.35 and protobuf 5.29.6, removing the audited protobuf 4.x resolution while preserving supported Python 3.10–3.12.

### Validation and limitations
- Automated tests cover synthetic control behavior, input fault injection, GUI construction/settings persistence, and initialization/inference of the bundled model.
- Automated checks are not a substitute for webcam, Windows desktop, comfort, or long-session validation.
- Pillow 13 is constrained to Python 3.11+ because its published package requires Python 3.11. Python 3.10 remains supported but may resolve an advisory-affected Pillow 12.x through transitive dependencies; see `SECURITY.md`.
- No signed installer or release executable is published by this change.

## 2.5.3 — Persistent Preview Window

### Fixed
- The OpenCV preview is now configured to stay above other windows by default, so it remains visible while users interact with a browser, document editor, or desktop application.
- On Windows, native `SetWindowPos` with `SWP_NOACTIVATE` reinforces topmost status without intentionally stealing focus from the foreground application.
- If the preview is accidentally minimized while always-on-top mode is enabled, the app periodically attempts to restore it without activating it.

### Added
- `preview_always_on_top` configuration option, enabled by default.
- `O` hotkey to toggle the preview's always-on-top behavior during a session.
- A regression test for topmost/restore behavior using a mocked Windows API, plus hotkey persistence tests.

### Validation
- Automated tests validate window-manager calls and application hotkey behavior without requiring a Windows desktop. Real multi-window behavior should still be confirmed on the target PC.


## 2.5.2 — Scroll Transition Dispatch Fix

### Fixed
- Scroll samples are now accepted only when both the confirmed gesture and the current raw frame classify as `TWO_FINGERS`. A transition frame that has already begun changing into POINT or another pose can no longer feed its fingertip movement into the scroll engine while gesture consensus is catching up.
- The controller independently enforces the same raw-pose guard, so it cannot fall back to cursor coordinates and treat a transition frame as scroll input.

### Added
- End-to-end regression coverage for a raw POINT transition while the confirmed gesture is still TWO_FINGERS.
- Controller-level coverage proving that a non-two-finger raw pose cannot produce a scroll event, even if a scroll coordinate is supplied.

### Validation
- The full test suite passes in the packaged source checkout. Webcam-specific behavior still needs to be verified on the target Windows machine.

## 2.5.1 — Scrolling Fix

### Fixed
- **Scrolling was extremely slow.** On Windows, PyAutoGUI passes the scroll amount straight through as the raw wheel delta, where one wheel notch is 120. The old code sent 1 to 6, at most about 5% of a notch, so a full stroke moved the page by a fraction of a line.
- **Scrolling was unreliable.** The old "one pulse per stroke" design locked after each scroll until the hand had settled within a few pixels near the start, which needs a pause of roughly 200 ms or more. With a natural flick-and-return rhythm only about 1 stroke in 10 registered.

### Changed
- Scrolling is now **rate-based**: the height where the two-finger pose begins is the neutral point, and holding your hand above or below it scrolls continuously, faster the farther you go. Returning to neutral stops, so there is no return-stroke problem and nothing to re-arm. The neutral point follows slow drift, and a stalled frame can never cause a burst.
- Scroll distances are measured as if the screen were 1080 px tall, so feel no longer depends on monitor resolution.
- Non-Windows platforms receive whole notches, matching what PyAutoGUI expects there.
- On the same simulated hand movement: a 1-second hold 100 px from neutral went from about 0.03 notches to about 6.7 notches, and 10 flick-and-return strokes went from 1 registering to all 10 registering.

### Settings
- New: `scroll_max_speed`, `scroll_full_speed_px`, `scroll_wheel_step`, `scroll_invert`. `scroll_deadzone_px` is now also the neutral-zone size.
- Removed (ignored if present, so existing settings files still load): `scroll_trigger_px`, `scroll_rearm_radius_px`, `scroll_rearm_stable_frames`, `scroll_gain`, `scroll_reversal_delay_s`, `two_finger_hold_for_scroll_s`.

### Notes
- Verified by simulation and automated tests only; please confirm the speed and dead zone feel right on your own camera. If scrolling is still too slow or too fast, adjust `scroll_max_speed` and `scroll_full_speed_px`.

## 2.5.0 — Polish Pass

### Fixed
- **Reaching a screen corner with your hand no longer pauses control.** The edge of the active region mapped to the exact corner pixels, which PyAutoGUI treats as emergency fail-safe points, so going for a window's close button could trip it. Hand-driven movement now stays `screen_edge_inset_px` (default 2) from the edges; the physical-mouse fail-safe still works.
- **The cursor no longer follows the curling fingertip just before a click or fist.** Pointer movement now also requires that the current frame looks like pointing, not only the (slightly delayed) confirmed gesture.
- Cursor coordinates are rounded instead of truncated, removing a constant half-pixel bias toward the top-left.
- Closing the preview window with its close button now quits. Previously the loop kept running and re-opened the window.
- HUD notifications containing "—" rendered as "?" (OpenCV cannot draw non-ASCII); text is now sanitized.
- Settings are found relative to the project instead of the working directory, so shortcuts and launching from another folder work. Boolean values are no longer accepted for integer settings.
- The README claimed open palm pauses control; it only rests the pointer. Documentation now matches behavior (`P` pauses).
- Removed leftover "AirTouch X" branding from the window title, HUD, and messages; the package is now simply `nomouse`.

### Added
- Redesigned preview HUD: status card with ACTIVE / PAUSED / SAFETY HOLD, color-coded gesture, FPS and latency, fading toasts, corner-bracket active region, and an on-demand gesture guide (`H`). It scales with the frame size and only blends the pixels it covers.
- Hotkey changes (`+`/`-`, `L`) are saved on exit (disable with `--no-save`). Settings are written atomically.
- Command line: `--config`, `--camera`, `--no-save`, `--version`; `python -m nomouse`; a `nomouse` console command when installed with pip. Pip-installed copies keep settings in `%APPDATA%\NoMouse` rather than inside site-packages.
- `Esc` also quits. `show_help_on_start` and `screen_edge_inset_px` settings.
- Friendly one-line errors for a missing webcam or missing dependency instead of a traceback.
- The installer rejects 32-bit Python; launchers pass arguments through.

### Developer experience
- `run()` split into a testable `GesturePipeline`, `handle_key`, and thin loop. Tests grew from 46 to 95, adding end-to-end pipeline tests with synthetic hands and a headless full-loop test with a fake camera, including "camera dies mid-drag releases the button".
- Dev dependencies moved to `requirements-dev.txt`; runtime `requirements.txt` is now runtime-only. `pyproject.toml` gains package discovery, console script, dynamic version/dependencies, and Ruff config.
- GitHub Actions workflow (Windows + Linux, Python 3.10–3.12) runs lint and tests without a webcam or MediaPipe.

### Notes
- Gesture recognition, scrolling, and filter algorithms are unchanged. The two cursor-behavior changes above (edge inset, no movement on transition frames) should be confirmed on your own camera.

## 2.4.0 — Stability Pass

- Tolerate one transient UNKNOWN classification/missing-hand frame without immediately destroying the active gesture consensus. Ambiguous frames do not dispatch mouse actions.
- Persistent UNKNOWN resets the confirmed gesture and triggers controller recovery.
- Scrolling recovery requires a stable position before re-arming near the original stroke baseline; merely passing through the recovery band no longer rearms it. Tightened the stability threshold so slow return drift is less likely to be mistaken for a new stroke.
- Added regression tests for transient UNKNOWN handling and scroll recovery through the origin band.

## 2.3.0 — Butter Responsiveness Pass

- Corrected One Euro filter velocity estimation.
- Avoided duplicate cursor updates.
- Added independent scroll filtering and stable recovery-locked scrolling.
- Improved configuration validation and camera failure cleanup.
