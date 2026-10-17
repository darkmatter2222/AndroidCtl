# Local device workbench

A compact dark browser utility for connected USB/emulator/network ADB devices. Saved endpoints remain visible when offline. Drag tile headers to reorder (saved per browser), adjust tile width, focus a screen, pause previews, inspect Android properties/battery/display, and launch native scrcpy. Each tile displays transport status and frame timing/size. With an explicitly configured AndroidCtl host, it also starts/stops/creates/deletes managed instances.

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
- Browser preview: PNG screenshot polling every 1, 2 or 5 seconds, with only one outstanding request per tile. The page pauses capture when hidden; at most two captures and eight total ADB subprocesses run concurrently. Actual cadence depends on device/network/capture latency. This is not a 30/60 FPS video stream and has no audio.
- Turn **Input ON** for a tile to send taps, drags/swipes, Back, Home or Apps. Input coordinates map to the captured image's native pixel dimensions. Rotation between capture and input can invalidate coordinates: wait for the next frame. No keyboard text entry or multitouch in this version.
- **scrcpy ↗** opens a native video/control window on the machine running the Python service. It requires a desktop session and scrcpy on PATH. A running viewer is reused per serial. Launch reporting does not prove successful video initialization; inspect the terminal for scrcpy errors.
- **Inspect** reads properties, battery and display dimensions on demand. **Disconnect** saves the device automatically, stops preview requests, clears the stale frame, closes a scrcpy viewer launched by this server, and keeps a “disconnected” tile with **Connect** available. Network devices are disconnected from the shared ADB server; this also affects agents using that transport. USB/emulator serials without a network endpoint are detached from the workbench only, because ADB cannot disconnect one USB transport. They remain available to other tools. Workbench-only detach state lasts until reconnect or server restart.
- **Pause tile** stops only this browser tile's preview traffic, keeping ADB available for agents; **Resume tile** restarts capture. Global pause still works. Disconnect/pause does not stop Android or release its VM RAM/CPU.
- **Forget** removes a saved entry, without disconnecting it; connected devices remain discoverable.

### Restart and resolution

Each online tile reads its actual physical size/density once and populates a dropdown. **Read resolutions** refreshes these values manually. Options are **Keep current**, **Native default**, and 75%, 50%, 33%, 25% of native dimensions (rounded to even pixels). Density scales proportionally, with a minimum of 72 dpi. For a native 1344×2992 / 480 dpi device, 50% gives 672×1496 / 240 dpi and 25% gives 336×748 / 120 dpi. Native default resets both overrides; it is distinct from an already-overridden current size.

**Apply now** changes and reads back size/density without rebooting. **Restart** asks for confirmation, reboots only the selected Android guest, waits for a changed boot ID and `sys.boot_completed=1`, then applies and verifies the selected profile. The tile reports restart progress, completion or error and pauses screenshots during the job. Keep the Python server running until completion. The 240-second boot deadline is approximate because individual ADB commands can take up to 15 seconds. Network reconnection uses the same exact endpoint; wireless debugging may change its port after reboot, requiring manual reconnection. This does not restart the host systemd service and cannot recover an emulator that is already offline/crashed.

AndroidCtl host startup currently resets `wm` overrides. Applying after Android boot addresses guest restarts initiated here, but a later host/service restart or external display policy may reset the setting again. These are Android logical display overrides, not edits to the AVD hardware profile. If one display command fails, a partial override can remain; choose Native default / Apply now to recover. Reboot success is reported only after display readback matches.

Lower resolution reduces pixels to render/capture/transfer, but does not guarantee smooth video: browser previews still use screenshot polling. Pause unused tiles or disconnect unused network transports to reduce capture work. Coordinate with agents before rebooting or changing resolution, since old screenshot coordinates become invalid.

Pause or coordinate with any automation input owner before manual actions. The workbench does not enforce locks shared with android_automation agents.

## OpenCode and other agents

Use `.agents/skills/androidctl-workbench/SKILL.md` as the repository workflow. Ask OpenCode: “Start the AndroidCtl web workbench with `python -m androidctl.web --no-browser` and give me its local URL.” Existing `/androidctl` desktop plugin commands are unchanged. Keep the service running in an owned terminal/process session.

API contract (token in `X-AndroidCtl-Token`, no query-string tokens):

| Method / path | Payload or result |
|---|---|
| GET `/api/devices` | `{devices: [{serial, name, state, details?}]}` |
| GET `/api/frame?serial=...` | PNG bytes; URL-encode exact serial |
| POST `/api/action` | JSON object with `action`, `serial`, and fields below |

Additional actions: `display` returns native/current values and profile definitions; `resolution` applies a `profile` (`current`, `default`, `75`, `50`, `33`, `25`); `restart` accepts the same `profile` and returns immediately. Poll `/api/devices` for `operation.state` (`running`, `done`, `error`) and `operation.message`. During restart the device state is `restarting` and input/frame requests are rejected.

Actions: `save` (`name`), `forget`, `connect`, `disconnect`, `pair` (`code`), `info`, `scrcpy`, `key` (`key`: 3, 4, 24, 25, 26, 82, 187), `tap` (`points`: [x,y]), `swipe` (`points`: [x1,y1,x2,y2], fixed 300 ms). Failures return `{error: message}` and a non-2xx status. There is deliberately no arbitrary shell execution API. Input ON is a browser safeguard, not an API authorization boundary: token holders can control devices.

## Deployment and validation limits

This release targets a local desktop. No container recipe is provided: native scrcpy requires a desktop, USB requires explicit host-device access, and publishing a container port would undermine the loopback security boundary. Use a trusted remote desktop for server-hosted usage until authenticated remote hosting is designed.

Automated tests cover discovery, persistence, exact serial forwarding, input validation and HTTP authentication/origin boundaries. Hardware acceptance: connect two devices, verify both previews, reorder/focus, tap/swipe in a harmless app, rotate, unplug/reconnect, pair wirelessly, launch scrcpy, restart the utility, and confirm saved endpoints/layout survive. Windows/macOS live execution, physical devices, emulator graphics and live OpenCode integration still require host validation.

Research: [official scrcpy](https://github.com/Genymobile/scrcpy), [Tango browser scrcpy client](https://tangoadb.dev/scrcpy/), [ws-scrcpy](https://github.com/NetrisTV/ws-scrcpy). A future browser video transport can replace polling without changing device discovery or the control API. Screenshot polling was chosen here to keep installation portable and dependency-free; it is not equivalent to these video clients.


## Managed hosts and full instance lifecycle

Expand **Android instance hosts**. Save a nickname (for example `databrick`), SSH target (`user@hostname` or an existing SSH config alias), SSH port and the reachable ADB hostname/IP. Use `local` only when the web server is running on the Linux AndroidCtl host. No credentials are stored. SSH runs with BatchMode and strict host-key checking: establish and verify normal SSH connectivity first. Install/upgrade AndroidCtl on that host separately. Mutations call `sudo -n androidctl` and need an existing suitable noninteractive sudo policy; the utility does not edit sudoers or open interactive password prompts.

**Scan instances** queries `androidctl list --json`, including stopped VMs. Each managed tile shows host/instance ID, service state, renderer and allocated RAM/vCPUs. These tiles survive ADB disconnects because they come from host inventory. **Scan ADB** refreshes the current ADB server's transports; it does not scan your LAN or find powered-off machines. Host inventory is refreshed at the end of each host operation; use Scan instances for changes made elsewhere. On web-server restart, scan saved hosts again to repopulate managed-instance metadata.

- **Start instance** starts the selected persistent VM through AndroidCtl; then Connect opens its ADB transport. It does not silently start every VM.
- **Stop instance** confirms before completely stopping its emulator service, freeing its VM resources while preserving userdata. This differs from Disconnect or Pause tile.
- **Create instance** takes an unused ID 01–64, hardware profile, Android API, RAM MiB and CPU cores. It uses an already installed SDK image and leaves the new VM stopped. There is no unattended SDK download or license acceptance. Install required images on the host first.
- **Delete instance** requires typing `DELETE ID`, then explicitly choosing whether to erase userdata or preserve it. This invokes the host's stop-and-delete lifecycle logic. Preserved data prevents blindly recreating the same AVD name; see the host backup/restore guide. A previously saved ADB endpoint can remain as a disconnected tile; Forget removes that endpoint.
- **Set renderer (stopped)** selects host GPU or software SwANGLE. Stop the VM first. The host renderer command selects one NVIDIA GPU, or one Mesa GPU if no NVIDIA is present. Multi-NVIDIA hosts are not supported by the experimental NVIDIA path.
- **Performance report** runs the new read-only host report and displays the result under host status. See [RTX 3090 trial](gpu.md#rtx-3090-performance-trial-existing-instances). It does not stop models or edit drivers.

Only one management job runs per host at a time. Status and bounded command output appear in the host panel. Keep the server open during jobs. A command timeout or lost SSH session is not proof that the remote operation stopped: scan the host before retrying. Creation/deletion and renderer changes have not been tested on a real host by this development environment.

Host profiles persist alongside the device file as `web-hosts.json`. `GET /api/hosts` returns profiles, cached inventory and operation state. `POST /api/host-action` accepts: `save` (`id`, `target`, `endpoint_host`, `port`); `scan`/`diagnostics` (`host`); `start`/`stop` (`host`, `instance`); `create` (plus `profile`, `api`, `ram`, `cpus`); `renderer` (plus `gpu`: `host` or `swangle`); `delete` (plus exact `confirm`: `DELETE 01`, and boolean `erase_data`). The same local session token and origin checks apply. The remote command is built from allowlisted fields, not arbitrary shell text.

Browser capture concurrency is capped at two with separate capacity from input/control work, so a large grid cannot fill every ADB slot with screenshots. This reduces capture contention; it is not a guarantee that the Android guest itself will respond quickly.
