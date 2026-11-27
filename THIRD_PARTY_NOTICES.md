# Third-party notices

The repository's own source code remains under the MIT license in `LICENSE`. Runtime distributions additionally contain third-party code and data with their own terms; review the upstream notices before redistributing binaries.

## MediaPipe

The MediaPipe Python distribution is published by Google under the Apache License 2.0. The bundled Hand Landmarker model is obtained from the official MediaPipe model endpoint:

`https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task`

The model file is `nomouse/models/hand_landmarker.task` (SHA-256 `FBC2A30080C3C557093B5DDFC334698132EB341044CCEE322CCF8BCF3607CDE1`). See the upstream [MediaPipe repository license](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE) and [Hand Landmarker documentation](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker) for current terms and model details. This notice records provenance; it is not legal advice.

## PySide6 / Qt

PySide6 Essentials is the official Qt for Python binding. Qt/PySide open-source distributions are available under LGPLv3/GPLv3 terms, with a commercial license alternative. Building or redistributing a PyInstaller folder does not eliminate those obligations. Include the applicable license and notices, provide required relinking/source materials, and review Qt's current distribution requirements before publishing an executable.

## Other runtime dependencies

The pinned OpenCV, NumPy, PyAutoGUI, protobuf, Pillow, and transitive Python dependencies carry their own upstream copyright and license terms. Their licenses and advisories can change with version resolution. Use the installed package metadata and upstream project notices when preparing a release; this file is not an exhaustive SBOM.
