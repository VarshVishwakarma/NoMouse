# Contributing

Thanks for helping improve NoMouse. The project is MIT-licensed and welcomes focused bug fixes, usability improvements, documentation, and tests.

## Set up

Use 64-bit Python 3.11 on Windows for the recommended application environment:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m ruff check .
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m pytest -q
```

For non-Windows development, the pure logic and offscreen Qt tests run in CI, but do not assume OS mouse injection or camera/window behavior works on that platform.

## Change expectations

- Keep changes scoped and preserve working behavior.
- Add regression tests for changed logic, especially state transitions, error paths, and safety invariants.
- Use synthetic hand observations and fake mouse APIs for deterministic tests; do not make automated tests depend on an actual camera or desktop mouse.
- Keep PyAutoGUI's physical corner fail-safe enabled. Never suppress failed button releases or treat uncertain OS input as successful.
- Keep camera images and landmarks out of logs, exports, fixtures, and network services.
- Update the relevant user/architecture docs and changelog.
- Do not claim recognition accuracy or performance improvements without a reproducible dataset/measurement and stated test conditions.

## Pull requests

Include the user problem, the smallest solution, relevant test output, and any manual Windows/camera validation still required. Flag dependency and model changes with compatibility, licensing, and distribution notes. Do not include camera recordings, personal settings, secrets, generated build artifacts, or unsigned executables as if they were release artifacts.
