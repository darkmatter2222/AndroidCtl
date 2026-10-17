# Local device workbench

A compact dark browser utility for connected USB/emulator/network ADB devices. Saved endpoints remain visible when offline. Drag tile headers to reorder (saved per browser), adjust tile width, focus a screen, pause previews, inspect Android properties/battery/display, and launch native scrcpy. Each tile displays transport status and frame timing/size. This utility does not install or start Android emulators.

## Start on Windows, Linux or macOS

Install Python 3.10+, Android platform-tools (`adb`), and optionally scrcpy on the computer running the utility. From the repository:

```sh
python -m pip install -e .
androidctl-web
```

Quick checkout launchers: double-click `start-web.bat` on Windows or run `./start-web.sh` on Linux/macOS. Both use the checkout directly without a pip installation.

Equivalent portable command: `python -m androidctl.web`. On the Linux host manager, `androidctl web` also works. No Node build or third-party Python runtime dependencies are needed. Ctrl+C stops the HTTP service; devices and already-open native scrcpy windows remain running.

```sh
androidctl-web --port 8765 --adb /path/to/adb --scrcpy /path/to/scrcpy
androidctl-web --adb-port 5038 --adb /opt/android-sdk/platform-tools/adb
androidctl-web --no-browser
```

The web listener prefers port 8765. If that default is blocked/reserved or in use, it automatically asks the OS for an available port and opens the actual URL. `--port 0` always requests automatic selection. An explicitly specified nonzero port is honored without fallback. Windows `WinError 10013` at bind can indicate a reserved or exclusively held port; it does not mean the app needs administrator privileges. If even `--port 0` fails, check endpoint security policy rather than changing firewall/port reservations blindly.

Desktop ADB defaults to 5037. AndroidCtl's dedicated managed host server uses 5038; choose it explicitly. Existing devices on the selected ADB server are discovered automatically. To use remote configured fleet devices, run `androidctl fleet screen` on the host and add the reported endpoints here. This version does not automatically import OpenCode aliases or host instance configuration.

The command opens the browser and prints a URL containing a per-process session token. Reopen that complete URL after a restart; a stale tab's previous token will be rejected. The browser moves the token into session storage and removes it from the address bar. The service binds only to 127.0.0.1, validates Host/Origin, and requires the token for all API requests. No CORS, arbitrary shell endpoint, or public bind option is provided. Run as your normal desktop user, not root.

## Connect and control

- USB: enable USB debugging and approve the host's RSA prompt on the phone. Unauthorized/offline states appear in the grid.
- Network: enter `hostname:port`, optionally a name, **Save device**, then **Connect**. Saving alone never initiates a connection. Names/endpoints persist in `~/.androidctl/web-devices.json` (`--state` overrides this).
- Android wireless debugging: enter the pairing endpoint and six-digit code, choose **Pair**, then change to the separate debugging endpoint and choose **Connect**. Codes are never persisted.
- Browser preview: PNG screenshot polling every 1, 2 or 5 seconds, with only one outstanding request per tile. The page pauses capture when hidden; at most eight ADB subprocesses run concurrently. Actual cadence depends on device/network/capture latency. This is not a 30/60 FPS video stream and has no audio.
- Turn **Input ON** for a tile to send taps, drags/swipes, Back, Home or Apps. Input coordinates map to the captured image's native pixel dimensions. Rotation between capture and input can invalidate coordinates: wait for the next frame. No keyboard text entry or multitouch in this version.
- **scrcpy ↗** opens a native video/control window on the machine running the Python service. It requires a desktop session and scrcpy on PATH. A running viewer is reused per serial. Launch reporting does not prove successful video initialization; inspect the terminal for scrcpy errors.
- **Inspect** reads properties, battery and display dimensions on demand. **Disconnect** only targets the selected network endpoint. **Forget** removes a saved entry, without disconnecting it; connected devices remain discoverable.

Pause or coordinate with any automation input owner before manual actions. The workbench does not enforce locks shared with android_automation agents.

## OpenCode and other agents

Use `.agents/skills/androidctl-workbench/SKILL.md` as the repository workflow. Ask OpenCode: “Start the AndroidCtl web workbench with `python -m androidctl.web --no-browser` and give me its local URL.” Existing `/androidctl` desktop plugin commands are unchanged. Keep the service running in an owned terminal/process session.

API contract (token in `X-AndroidCtl-Token`, no query-string tokens):

| Method / path | Payload or result |
|---|---|
| GET `/api/devices` | `{devices: [{serial, name, state, details?}]}` |
| GET `/api/frame?serial=...` | PNG bytes; URL-encode exact serial |
| POST `/api/action` | JSON object with `action`, `serial`, and fields below |

Actions: `save` (`name`), `forget`, `connect`, `disconnect`, `pair` (`code`), `info`, `scrcpy`, `key` (`key`: 3, 4, 24, 25, 26, 82, 187), `tap` (`points`: [x,y]), `swipe` (`points`: [x1,y1,x2,y2], fixed 300 ms). Failures return `{error: message}` and a non-2xx status. There is deliberately no arbitrary shell execution API. Input ON is a browser safeguard, not an API authorization boundary: token holders can control devices.

## Deployment and validation limits

This release targets a local desktop. No container recipe is provided: native scrcpy requires a desktop, USB requires explicit host-device access, and publishing a container port would undermine the loopback security boundary. Use a trusted remote desktop for server-hosted usage until authenticated remote hosting is designed.

Automated tests cover discovery, persistence, exact serial forwarding, input validation and HTTP authentication/origin boundaries. Hardware acceptance: connect two devices, verify both previews, reorder/focus, tap/swipe in a harmless app, rotate, unplug/reconnect, pair wirelessly, launch scrcpy, restart the utility, and confirm saved endpoints/layout survive. Windows/macOS live execution, physical devices, emulator graphics and live OpenCode integration still require host validation.

Research: [official scrcpy](https://github.com/Genymobile/scrcpy), [Tango browser scrcpy client](https://tangoadb.dev/scrcpy/), [ws-scrcpy](https://github.com/NetrisTV/ws-scrcpy). A future browser video transport can replace polling without changing device discovery or the control API. Screenshot polling was chosen here to keep installation portable and dependency-free; it is not equivalent to these video clients.
