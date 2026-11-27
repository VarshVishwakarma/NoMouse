# NoMouse — portfolio showcase

## Project overview

NoMouse is an open-source, local-first desktop application for hands-free mouse input. It converts webcam hand landmarks into pointer, click, drag, scroll, and pause interactions. This release adds a Qt desktop shell around the pre-existing control pipeline and preserves a separately invokable command-line preview loop.

## Technology stack

- Python 3.10–3.12
- PySide6 Essentials / Qt Widgets
- OpenCV for webcam capture and image display
- MediaPipe Tasks HandLandmarker in VIDEO mode with a bundled task model
- NumPy, PyAutoGUI, pytest, Ruff, PyInstaller
- GitHub Actions for Windows/Linux logic checks, Windows dependency audit, and Windows package build

## Architecture

The Qt UI owns navigation, settings, onboarding, calibration guidance, and aggregate-only diagnostics export. A `QThread` worker owns camera capture, MediaPipe inference, gesture pipeline, and OS input. Hand landmarks flow through geometric classification, consecutive-frame consensus, adaptive cursor/scroll filters, a stateful controller, and the preview safety guard before PyAutoGUI input. Camera frames cross to the UI only as copied in-memory `QImage` values.

## Implemented and testable features

- Dashboard with embedded preview, Start/Pause/Stop, gesture/tracking status, session FPS, and processing p95.
- First-run six-step onboarding; in-app gesture guide and calibration/settings surfaces.
- Persistent, range-checked camera index/resolution/requested-FPS, cursor, pinch, click, drag, scroll, gesture-enable, landmark, and safety options.
- Official MediaPipe Tasks VIDEO tracker with locally bundled model and deterministic timestamp handling.
- Palm-center scroll anchoring, separate scroll filtering, and live scroll neutral recentering.
- Fail-closed input error handling with explicit potentially-held mouse-button state.
- Aggregate performance JSON export that omits images and landmark coordinates.
- Fault-injection, pipeline, settings, safety-guard, offscreen GUI, and model smoke tests.
- Windows PyInstaller onedir recipe and CI build smoke test configuration.

## Engineering decisions and challenges

1. **Keep the tested control core.** Qt presentation is added around the existing pipeline rather than moving gesture behavior into UI widgets.
2. **Do not migrate MediaPipe blindly.** The current Tasks release removed `mp.solutions`; the tracker now uses the documented Tasks VIDEO interface and a versioned-in-repository model asset instead of performing a hidden first-run download.
3. **Fail closed on uncertain input.** Track button-down intent before calling the native input API, try release on failure, preserve an uncertain state if release fails, and prevent re-enabling control in the same process.
4. **Use a steadier scroll reference.** Scroll position comes from the center of the palm landmarks rather than the index fingertip; a regression test proves fingertip-only movement does not change the chosen anchor. Real-user ergonomics remain unmeasured.
5. **Be precise about performance.** The application separates capture-read, model inference, decision, and software frame-processing time. It does not label these values as camera-to-screen latency or universal performance claims.
6. **Contain GUI threading risk.** A lock-protected preview-bounds snapshot lets the worker use the fail-closed safety guard without reading Qt widgets cross-thread.

## Automated test results

The final local run completed **131 tests successfully** (`py -3.10 -m pytest -q`) and Ruff reported **All checks passed** (`py -3.10 -m ruff check .`). `git diff --check` also passed. Tests are deterministic software checks using fake input/synthetic observations, including GUI worker startup-failure and camera/tracker cleanup cases, except the MediaPipe model smoke test, which initializes the bundled model and processes a synthetic blank image. None of these tests is a physical-camera usability study.

## Performance and hardware

No comparative performance benchmark, camera-to-screen latency measurement, long-runtime soak test, or user-accuracy study was performed. The live dashboard gathers per-session software timings, but no numeric result is asserted here. Windows camera access, native mouse behavior, scroll compatibility, preview obstruction, and ergonomics require manual testing on real hardware.

## Installation and packaging status

Source installation is documented through `install_windows.bat` and the Python package entry points. `pip-audit` reports **no known vulnerabilities** for the resolved Python 3.11 runtime dependencies; on Python 3.10 it reports **42 Pillow 12.3.0 advisory records**, fixed by Pillow 13.0.0 (Python 3.11+ only). A clean Python 3.10 Windows onedir build completed at **324.5 MB**, contains the bundled hand model, and its executable passed a `--version` launch check. This repository change is not a signed installer or published release artifact. Review Qt redistribution requirements before sharing an executable.

## Limitations and future opportunities

- No labeled real-world gesture dataset, confusion matrix, precision/recall, or false-activation rate exists.
- The gesture classifier is geometry-based and the camera environment strongly affects results.
- Camera options are indices, profiles are not multi-user, and calibration is guided/manual.
- The interface currently offers a dark theme only; keybinding remapping and device-name enumeration are not implemented.
- No Linux/macOS desktop-input support, mobile companion, telemetry, cloud service, or medical/accessibility efficacy claim is made.
- Python 3.10 may resolve an advisory-affected Pillow 12.x because Pillow 13 requires Python 3.11; see `SECURITY.md`.

## Resume bullets

- Built a PySide6 desktop interface for a webcam-based hand-control application, integrating an embedded live preview, worker-thread camera/inference loop, persistent settings, onboarding, and per-session diagnostics.
- Migrated hand tracking to MediaPipe Tasks VIDEO with a bundled offline model and added deterministic regression coverage for gesture transitions, palm-based scrolling, and configurable interaction controls.
- Hardened mouse-button recovery with fault-injected tests for ambiguous press/release failures, fail-closed controller shutdown, preview bounds protection, and an emergency-stop-preserving interaction path.

These bullets describe implemented source and automated test coverage; they do not claim user adoption, measured accuracy gains, physical accessibility validation, or signed distribution.

## LinkedIn announcement draft

> I’ve been rebuilding NoMouse, my open-source webcam hand-control project, into a real desktop application. The new version adds a PySide6 dashboard with an embedded preview, a worker-thread camera/control pipeline, persistent settings and calibration guidance, local MediaPipe Tasks inference, session diagnostics, and regression tests for input failure recovery.
>
> One challenge was updating MediaPipe after its legacy `mp.solutions` API was removed. I migrated the tracker to Tasks VIDEO and bundle the model so runtime inference stays local. I also hardened drag recovery so an uncertain mouse release disables control and remains visible instead of being treated as success.
>
> The software tests now cover synthetic gestures, injected input failures, GUI settings persistence, and model initialization. Physical camera accuracy, comfort, and Windows application compatibility still need hardware testing. I’m sharing the code and limitations transparently as I continue validating it.

## Interview explanation

“The UI and real-time loop are deliberately separated. A Qt main thread handles navigation and receives copied preview images and aggregate metrics. A worker owns the camera, MediaPipe Tasks VIDEO landmarker, existing gesture pipeline, and input controller. The pure geometry, filter, consensus, and scrolling logic remains independently testable. Before OS input, the controller checks preview bounds and retains PyAutoGUI's emergency fail-safe. For drag, it records a possible held button before `mouseDown`; if any native input operation fails, control is disabled, release is attempted, and an unconfirmed release remains explicitly latched. I chose a palm-center scroll reference to reduce the effect of fingertip motion, but I have not claimed real-user accuracy or hardware performance until those tests are run.”
