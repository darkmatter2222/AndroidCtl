# Four Pixel 8 Pro devices

The native portrait display is **1344 × 2992 pixels**. Google specifies this
panel resolution at [Pixel hardware specifications](https://support.google.com/pixelphone/answer/7158570).
The emulator profile's logical density is 480 dpi; Google's physical panel
489 PPI is a different measurement. We do not substitute 489 for Android density.

Fleet setup configures AVD hardware width/height and skin, then launch pins
the emulator display with `-skin 1344x2992 -dpi-device 480`. Every boot resets
persistent Android `wm size` and `wm density` overrides (including the earlier
672x1496/240 experiment), and refuses readiness unless `wm size` reports
Physical size: 1344x2992 with no override. Rotation can exchange width/height.
See [official emulator command-line options](https://developer.android.com/studio/run/emulator-commandline).

## Upgrade the existing installation

From your existing checkout (its directory may still be called virtual_android):

```bash
sudo androidctl stop 01
# Stop any other existing managed instances too before upgrading.
git remote set-url origin https://github.com/darkmatter2222/AndroidCtl.git
git pull --ff-only
sudo ./upgrade.sh
sudo androidctl fleet setup
sudo androidctl fleet start
sudo androidctl fleet status
sudo androidctl fleet watch
```

For a fresh host, clone AndroidCtl and run `sudo ./install.sh` instead of
upgrade.sh, accepting SDK licenses, then run the same fleet setup/start commands.
Setup defaults to API 35 for all four devices; `fleet setup --api 34` selects
another API for a new fleet. Existing devices with a different API/profile
cause a refusal, never replacement. Image installation can require network access.

Setup preserves existing device 01 and its userdata, creates missing 02–04,
backs up edited AVD/instance/global configs, and raises the concurrency ceiling
to at least four. All managed instances must be stopped for setup. It is
rerunnable after a partial failure; already-created data is retained.
Default allocations are 4 GiB/four vCPUs per newly created device; existing
resource allocations remain intact. Four instances therefore ordinarily request
16 GiB guest RAM plus host/renderer overhead. CPU rendering at full resolution
can be demanding; throughput is not guaranteed by memory capacity alone.

Setup selects the session-tested SwANGLE workaround and disables guest Vulkan
per instance via `-feature -Vulkan`; no new shared feature-file edit is needed.
An existing service-account Vulkan=off file is preserved. Apps requiring guest
Vulkan may not run. This software rendering does not use the RTX 3090.
The earlier single-device success does not establish four-device performance.

## Daily commands

| Goal | Command |
|---|---|
| Start all four | `sudo androidctl fleet start` |
| Start selected devices | `sudo androidctl fleet start 1 3` |
| Stop all four | `sudo androidctl fleet stop` |
| Stop just device 2 | `sudo androidctl fleet stop 2` |
| Restart device 2 | `sudo androidctl fleet restart 2` |
| Count/list states, IDs, endpoints and restarts | `androidctl fleet status` |
| Follow fleet state log | `sudo androidctl fleet watch` |
| Print Windows screen commands | `androidctl fleet screen 1` |
| Android shell | `androidctl shell 01` |
| Device/emulator logs | `sudo androidctl logs 01 --follow` |
| Start all at host boot | `sudo androidctl fleet enable` |
| Disable host-boot startup | `sudo androidctl fleet disable` |

Start/stop/restart queue a single systemd transaction and return immediately.
They do not promise all guests are already healthy: use status/watch.
Repeated fleet start is safe for already-active units. Admission remains
enforced; failures stay visible, and successful devices are not rolled back.
Devices run concurrently, independent of SSH, with no tmux/nohup required.
Closing the watch console or pressing Ctrl+C stops observation only.
Host reboot is different from SSH disconnect: opt into boot startup with enable.
Individual existing androidctl lifecycle commands remain available.

## Remote screens

Defaults (saved port overrides remain authoritative):

| ID | Console | Local ADB | LAN ADB |
|---|---:|---:|---:|
| 01 | 5554 | 5555 | 15551 |
| 02 | 5556 | 5557 | 15552 |
| 03 | 5558 | 5559 | 15553 |
| 04 | 5560 | 5561 | 15554 |

Run `androidctl fleet screen` over SSH to print each endpoint and its client
commands. Execute those commands on Windows where adb/scrcpy are installed.
They omit `--max-size`, preserving full-resolution capture; resizing the desktop
window does not change the guest resolution. Each command opens one device;
use separate Windows terminals for all four.

Setup preserves the bind address. For LAN access, while all devices are stopped,
run `sudo androidctl config set bind_address auto` (or an explicit private address)
before starting. Restrict access to your trusted LAN/VPN; the tool does not
change firewall rules. See [remote ADB](remote-adb.md).

## Persistent monitoring and logs

Setup enables `android-fleet-monitor.service` at host boot and starts it now.
It samples systemd state every 10 seconds and writes state changes and
60-second heartbeat records to `<log_root>/fleet.jsonl`
(default `/var/log/androidctl/fleet.jsonl`). Files rotate at 5 MiB with five
backups, approximately 30 MiB maximum total. Read with sudo. Records include
UTC timestamp, ID, state/substate, PID, restart count, result, exit status,
proxy status and remote port. stdout also goes to journald for fleet watch.

This is an observer, not a guest watchdog: it never starts intentionally
stopped devices. Existing systemd Restart=on-failure handles emulator crashes
with its three-start/five-minute limit. A guest hang without process exit is
not automatically restarted. Polling may miss brief transitions; PID/restart
changes help detect them, and per-device journals are authoritative event logs.
Fleet status also checks Android boot/proxy readiness; monitor records do not
claim that an active process guarantees responsive Android.

Monitor service failure uses bounded restart. Check it using
`sudo systemctl status android-fleet-monitor.service`.
To stop monitoring: `sudo systemctl disable --now android-fleet-monitor.service`.
This does not stop devices. Upgrade restarts an enabled monitor; uninstall
disables/removes it while preserving logs and device data by default.

## Verify on the actual host

After boot, for each 01–04 run:

```bash
androidctl adb 01 shell wm size
androidctl adb 01 shell wm density
```

Expect physical size 1344x2992, physical density 480, no overrides. Confirm
startup logs show the ANGLE adapter. Connect all four, exercise the normal
workload, disconnect SSH and reconnect, then compare fleet status/PIDs/restarts.
Intentionally stop one and check that a state-change record appears and it
stays stopped. These KVM/graphics/load checks cannot be established by unit tests.

To undo fleet display enforcement, stop the devices and restore the timestamped
instance/AVD config backups created by setup, then restart. Restore global
capacity only if appropriate for the remaining fleet. No userdata wipe is needed.
