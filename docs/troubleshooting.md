# Troubleshooting

| Symptom | Checks and action |
|---|---|
| Missing `/dev/kvm` | Enable firmware virtualization; inspect KVM modules. On a VM, confirm supported nested KVM. No software CPU emulation fallback is used. |
| Acceleration denied | Run `sudo androidctl doctor`; check the configured service account's kvm group membership and device permissions. |
| Profile unavailable | Use `androidctl profiles`; upgrade command-line tools or explicitly choose a listed profile. |
| Image unavailable | Inspect `androidctl sdk images`; image variant/architecture availability differs by API. |
| SDK license rejected | Run `sudo androidctl sdk licenses`, review/accept, retry installation. |
| Port occupied | Follow the error's `sudo ss -ltnp 'sport = :PORT'` command. Change the conflicting workload or explicitly choose unused permanent ports. |
| Starting/booting never healthy | Inspect `sudo androidctl logs ID --follow`; Android must finish boot and the proxy must start. |
| Renderer crash | Inspect selected GPU, service device policy and graphics libraries; try a supported software renderer while stopped. |
| Start limit hit | Repair the cause, then `sudo systemctl reset-failed android-emulator@ID.service` and start again. |
| Resource limit | Check `MemAvailable`, configured RAM/reserve and active devices. Reduce load or deliberately use `start ID --force`. |
| Remote client refused | Default bind is loopback. Check endpoint, proxy journal, existing firewall policy and LAN address. Use SSH tunneling if appropriate. |
| ADB offline | Check managed `android-adb.service` journal, emulator boot logs and `androidctl adb ID get-state`. |
| scrcpy audio fails | Add `--no-audio`; inspect client-supported encoders/options. |
| Creation interrupted | Inspect retained AVD data and pointer. Retry refuses to overwrite them; recover config or explicitly remove only confirmed disposable orphan data. |
| Forced shutdown warning | Inspect journal and storage health before restarting. SIGKILL is the last systemd escalation, not normal operation. |
| CLI works but boot autostart GPU fails | Regenerate unit policies with offline `upgrade.sh` after manual GPU config edits. |

Useful commands: `sudo androidctl doctor --json`, `androidctl status ID --json`, `sudo journalctl -u android-adb.service`, `sudo systemctl status android-emulator@ID.service`, and `sudo ss -ltnp`.

Do not post unredacted diagnostics publicly: local hostnames, interface addresses, serials, paths and application data may be present. Never upload `.android/adbkey`, full AVDs or private configuration as an issue attachment.

## Emulator crashes, restarts, then ADB stays offline

### Observed incident (2026-10-08)

An API 35 Google APIs x86_64 device (Android 15, Pixel 8 Pro profile,
4096 MB guest RAM, four vCPUs) running Android Emulator 37.2.12.0
(build 16428233) with `gpu_mode = software` repeatedly crashed.
The relevant sanitized evidence was:

```text
bad color buffer handle 305
vulkan_mode_selected:lavapipe gles_mode_selected:swangle
Main process exited, code=dumped, status=11/SEGV
Result=core-dump
NRestarts=3
MainPID=0
Start request repeated too quickly
```

The host had approximately 59 GiB available RAM and 2.9 TB free disk;
the supplied kernel-log excerpt did not show an OOM kill. The evidence
confirms a host emulator segmentation fault followed by systemd's restart
limit, not merely a stale Windows ADB connection. The proxy stopped when
its emulator dependency failed. ADB connection-refused/offline messages
were downstream symptoms.

Graphics errors and the selected Lavapipe/SwANGLE path make the renderer
a leading suspect, but no core backtrace was supplied to identify the
faulting library. Explicit SwiftShader is a targeted workaround to test,
not a confirmed fix for this emulator version. At documentation time,
the configuration edit had succeeded; successful boot and sustained
workload stability after that edit had not yet been reported.

### Capture evidence before recovery

Examples below target instance 01. Substitute the affected instance ID.

```bash
sudo androidctl status 01 --json
sudo systemctl show android-emulator@01.service \
  -p ActiveState -p SubState -p Result -p NRestarts \
  -p ExecMainCode -p ExecMainStatus -p MainPID

sudo journalctl \
  -u android-emulator@01.service \
  -u android-adb-proxy@01.service \
  -u android-adb.service \
  --since "30 minutes ago" --no-pager -n 350

sudo journalctl -k --since "30 minutes ago" --no-pager \
  | grep -Ei 'oom|out of memory|killed process|segfault|NVRM|Xid|kvm|I/O error'

free -h
df -h /var/lib/androidctl
```

For a retained core, use `sudo coredumpctl list --since "30 minutes ago"`,
then `sudo coredumpctl info <CRASHED_PID> --no-pager`. Use the emulator PID
from the incident, not the currently running replacement. Core retention
depends on the host's crash handler; no matching core is also a useful
result. Do not upload a full core or unredacted logs publicly.

### Try explicit SwiftShader for this software-rendering instance

Google documents `swiftshader` as software rendering for GLES and Vulkan:
[Emulator graphics acceleration](https://developer.android.com/studio/run/emulator-acceleration).
This remains CPU software rendering; it does not enable a physical NVIDIA
GPU. Do not increase RAM or open firewall rules as a remedy for a segfault.

The following uses the default configuration path, backs up the instance
configuration, and changes only its renderer. Normal startup preserves
apps and userdata. This procedure is specifically a software-to-software
change; physical GPU changes also require the appropriate device policy.

```bash
sudo bash <<'BASH'
set -euo pipefail
systemctl stop android-emulator@01.service

cfg=/etc/androidctl/instances/01.conf
cp -a "$cfg" "$cfg.backup-$(date +%Y%m%d-%H%M%S)"

python3 - <<'PY'
from pathlib import Path
import re

p = Path("/etc/androidctl/instances/01.conf")
text = p.read_text()
updated, count = re.subn(
    r"(?m)^[ \t]*gpu_mode[ \t]*=.*$",
    "gpu_mode = swiftshader",
    text,
)
if count != 1:
    raise SystemExit("Expected exactly one gpu_mode setting; no changes made.")
p.write_text(updated)
print("Updated instance 01: gpu_mode = swiftshader")
PY

systemctl reset-failed android-emulator@01.service
androidctl start 01
androidctl status 01 --json
BASH
```

**Correction to the initial recovery script:** do not unconditionally
reset both emulator and proxy units in a fail-fast script. The incident
returned `Unit android-adb-proxy@01.service not loaded`; that made
`systemctl reset-failed` return an error and `set -e` exited before startup.
The renderer edit had already succeeded. To continue from that exact state:

```bash
sudo systemctl reset-failed android-emulator@01.service
sudo androidctl start 01
sudo androidctl status 01 --json
```

The emulator unit requests its proxy automatically. If the proxy itself
has a recorded start-limit failure, inspect and reset that loaded unit
separately, then start it after the emulator is healthy. A genuinely
missing unit file is an installation issue, distinct from an unloaded unit.

### Reconnect Windows and validate

Replace `<ANDROID_HOST>` with the address printed by
`androidctl adb-endpoint 01`.

```cmd
adb disconnect <ANDROID_HOST>:15551
adb connect <ANDROID_HOST>:15551
adb -s <ANDROID_HOST>:15551 get-state
scrcpy -s <ANDROID_HOST>:15551 --no-audio --video-codec=h264 --max-size=1024 --max-fps=30 --print-fps
```

Expect `device` from ADB and `gpu_mode: swiftshader`, `health: healthy`
from AndroidCtl. Check the new startup journal to verify the actual selected
renderer, then repeat the app/activity that preceded the crash. A successful
boot alone is not proof of sustained stability. If it crashes again, collect
the new journal and core details before trying further changes.

Leave the restart limit in place: increasing it prolongs a crash loop.
To roll back the renderer, stop instance 01, restore the exact timestamped
configuration backup created above to `/etc/androidctl/instances/01.conf`,
reset the emulator's failed state, and start it. Restoring the old renderer
may restore the original crash behavior.

### Related performance and recovery notes

- `0 fps` alone does not prove a crash; the emulator exit status and journal
  establish the failure in this incident.
- The user had set `wm size 672x1496` and `wm density 240`. Startup still
  logged a physical display of 1344x2992 at 480 dpi. Android's logical
  overrides and scrcpy's output scaling are distinct from the configured
  physical emulator display; these logs do not prove the overrides vanished.
  Inspect them with `androidctl adb 01 shell wm size` and
  `androidctl adb 01 shell wm density`.
- Current startup code waits for Android boot and applies postboot settings.
  It does not implement continuous ADB health recovery. The health command
  reports status; it is not a watchdog. A possible future improvement is
  bounded per-instance monitoring, targeted ADB reconnect, diagnostic
  capture, and restart only after sustained failure. This is not implemented
  by this documentation change and does not resolve a renderer segfault.
