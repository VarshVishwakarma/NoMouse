# Security policy

## Reporting

Please do not publish credentials, private camera footage, or an unpatched exploit in a public issue. If GitHub's private vulnerability reporting is enabled for this repository, use the repository's **Security → Report a vulnerability** flow. Otherwise contact the maintainer through their GitHub profile and include only the minimum reproduction details needed for triage. No response-time guarantee is currently offered.

## Product security boundaries

- Camera processing and gesture inference are local. The application does not provide cloud services, telemetry, account storage, or recording.
- Diagnostic exports contain session aggregates and a small set of configuration values, not frames or landmarks.
- PyAutoGUI's physical corner fail-safe stays enabled. The preview guard blocks actions when preview bounds are unknown.
- OS input failures disable control. If mouse-button release cannot be confirmed, NoMouse reports the uncertain held state and requires a restart; the user should verify the physical input state.
- The project is not a security-certified assistive technology or a substitute for operating-system accessibility tools.

## Dependency review

Direct application dependencies are pinned in `requirements.txt`; the CI workflow audits the resolved runtime set on Windows with Python 3.11. Review changes in MediaPipe, OpenCV, PyAutoGUI, PySide6/Qt, protobuf, Pillow, and their native binaries before updating versions. Validate supported Python versions, API behavior, wheel availability, license obligations, and the tracker model before merging.

The legacy MediaPipe 0.10.21 dependency constrained protobuf below version 5, which resolved to advisory-affected protobuf 4.x. NoMouse now uses MediaPipe 0.10.35 Tasks VIDEO and explicitly requires protobuf 5.29.6 or later within major version 5; the bundled model initialization and frame-processing smoke test validates the installed API.

**Python 3.10 residual:** The resolved Python 3.10 dependency set contains Pillow 12.3.0; the current audit reports 42 advisory records, each fixed by Pillow 13.0.0, which declares Python `>=3.11`. The project keeps Python 3.10 compatibility, so its transitive dependency resolution retains the affected Pillow release. NoMouse does not decode user-provided files through Pillow, but that does not remove the package-level risk. Python 3.11+ receives the Pillow 13 constraint and the current resolved dependency audit is clean. Reassess the minimum Python version and upstream fixes before claiming a clean audit across all supported interpreters.

The audit result is version- and interpreter-specific. A passing Python 3.11 dependency job does not prove that the Python 3.10 dependency set is vulnerability-free or that native libraries have no vulnerabilities.
