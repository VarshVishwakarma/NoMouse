# NoMouse user guide

## Before starting

Use a well-lit room and place the camera near eye level. Keep your hand inside the preview and start with your palm facing the camera. Use a harmless test window for initial clicks and scrolling, and keep a physical mouse nearby.

On the first launch, follow the six-page welcome guide. You can reopen gesture help from the Guide page at any time.

## Start and stop

1. Select the camera index, resolution, and requested capture rate in **Settings** while the session is stopped. Some camera drivers may ignore the requested FPS.
2. Select **Start control**. The camera, hand tracker, and controller run on a worker thread; the preview stays embedded in the dashboard.
3. Use **Pause** to stop sending input while keeping the session open. Resume when ready.
4. Use **Stop** to end tracking, release any held drag, close the camera, and return to idle.

Press the physical mouse into a screen corner to activate PyAutoGUI's emergency fail-safe. NoMouse keeps that fail-safe enabled. If an input-release error occurs, the controller disables itself and asks you to restart the application; check the physical mouse state before continuing.

## Gestures

| Gesture | Result |
|---|---|
| Index finger extended | Move cursor |
| Brief thumb-index pinch | Left-click |
| Hold thumb-index pinch | Drag; separating releases |
| Two extended fingers, still tap | Right-click |
| Two extended fingers, move vertically | Scroll relative to the gesture's neutral palm position |
| Four fingers, thumb tucked | Browser back (optional; enabled by default) |
| Open palm or fist | Rest without mouse action |

Change gesture availability and click/drag thresholds in Settings. Two quick pinches act as two normal clicks; the operating system decides whether they count as a double-click.

## Calibrate movement and scrolling

Start the camera and open **Calibration**:

1. Center your hand, then try cursor movement with the index finger extended.
2. Set **Cursor boundary** to limit the usable camera region. Increase it if you have a small comfortable movement range.
3. Adjust **Cursor stability**. Higher values smooth stationary jitter but can add lag; use the smallest value that feels steady.
4. Set maximum scroll rate. Test on a harmless page before increasing it.
5. Hold two fingers steady at the position you want as scroll neutral and press **Recenter scroll neutral**. The control confirms the baseline only while the two-finger pose is active.
6. Save calibration. Settings persist to the configuration file shown in the README.

The calibration page guides adjustment; it does not automatically infer a personalized gesture model or record video.

## Settings

Settings are range-validated and written atomically. Stop the live session before applying changes. **Restore defaults** resets the available controls to the built-in profile. The camera selector is an index, not a discovered device name; try another index if a virtual camera or external webcam occupies the default.

The preview safety switch blocks action dispatch over the preview area. Leave it enabled unless you understand the consequences. When the application cannot establish the protected preview bounds, the guard blocks the action.

## Diagnostics and privacy

Session diagnostics show capture-read, inference, and gesture/controller timings; FPS; software-processing p50/p95; intervals longer than the 30-FPS target; and tracking interruptions. These values describe this session and hardware only.

Export writes JSON containing aggregates, platform/version information, and limited settings. It does not record frames or export landmarks. Processing is local; NoMouse does not send telemetry or camera data.

## Troubleshooting

| Problem | Check |
|---|---|
| Camera will not open | Allow camera access in Windows privacy settings, close other camera apps, and try another device index. |
| No hand is detected | Improve lighting, move the hand into the preview, and face the palm toward the camera. |
| Pointer shakes | Increase smoothing slightly or reduce fast hand movement. |
| Pointer feels delayed | Lower smoothing; also check the Dashboard FPS and inference time. |
| Scroll starts at an awkward height | Hold two fingers steady at a comfortable neutral position and press **Recenter scroll neutral**. |
| Scroll is too fast/slow | Adjust maximum scroll rate and deadzone in Settings, then test in a harmless page. |
| A click or shortcut is not sent | Confirm the gesture is enabled, the pointer is not over the preview, and the session is not paused. |
| Session reports an input error | Control is disabled. Verify the physical mouse button is released, stop/restart NoMouse, and use the physical mouse until normal. |
| Setup or imports fail | Use 64-bit Python 3.11 and rerun `install_windows.bat`; run `diagnose_windows.bat` for dependency details. |

## Manual hardware validation checklist

This is a checklist, not evidence that these tests have been completed:

- Confirm the selected camera, focus, exposure, and preview orientation.
- Move the cursor around the safe region and verify the four screen corners do not trigger the emergency stop.
- Try left-click, short/long pinches, drag release, Pause, Stop, and physical fail-safe.
- Scroll up and down slowly and quickly; recenter, reverse direction, and verify neutral stops movement.
- Verify actions are blocked while the pointer is over the embedded preview.
- Repeat after camera disconnection and for a prolonged session; record any comfort or tracking issues.
