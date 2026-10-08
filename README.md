# AndroidCtl — native Android virtualization host

Manage persistent Android virtual devices like small VMs: `create`, `start`, `stop`, `restart`, `list`, `status`, `logs`, and `adb`. Each device has its own Android version, userdata, official hardware profile, and permanent ports.

AndroidCtl uses the **official Android Emulator, native KVM, Python's standard library, and systemd**. Android runs directly on the Ubuntu host. Existing Docker services, networking, GPU drivers, and firewall rules are not changed.

**Release status:** v0.1.0 implementation with automated non-hardware tests. Real KVM boot, graphics, LAN ADB, and reboot persistence must be validated on your host before relying on it. See [validation](docs/validation.md).

## Four-device fleet: install, upgrade, and run

Devices **01–04** run concurrently under systemd and survive SSH disconnects.
Their native virtual display is **1344×2992**, the Pixel 8 Pro panel resolution,
with emulator logical density **480 dpi**. This is the Android display itself,
not a scrcpy window size. Setup pins the AVD hardware/skin and resets old
`wm size`/`wm density` overrides at every boot, including the earlier
672×1496/240 experiment. Readiness requires the expected physical resolution.

### Stop existing devices before upgrading

SSH into your Ubuntu host (for example, `ssh <USER>@<ANDROID_HOST>`).
These synchronous commands stop all loaded AndroidCtl emulator/proxy services,
including IDs outside 01–04, and work with installations predating fleet commands:

```bash
sudo systemctl stop 'android-emulator@*.service'
sudo systemctl stop 'android-adb-proxy@*.service'
```

Check for leftover processes and listeners:

```bash
sudo ps -eo user,pid,ppid,args | grep -E '[q]emu-system|[/]opt/android-sdk/emulator|[s]ocat'
sudo ss -ltnp | grep -E ':(555[4-9]|556[01]|1555[1-4])\b'
```

No matching output is normal when nothing remains. For each suspected leftover,
replace `PID` below with its actual numeric PID and inspect its owner, command,
and supervising service:

```bash
sudo systemctl status PID
sudo ps -p PID -o user,pid,ppid,args
```

If it belongs to a service, stop that specific service first. For a confirmed
orphaned Android emulator, use `sudo kill -TERM PID`, then repeat the checks.
Do not blanket-kill QEMU or socat: other workloads may use them. If a process
returns, identify and stop its supervisor before continuing. Preserve userdata;
cleanup does not require deleting AVDs.

### Upgrade an existing host

For an existing checkout such as `~/virtual_android`, after stopping all devices:

```bash
cd ~/virtual_android
git remote set-url origin https://github.com/darkmatter2222/AndroidCtl.git
git pull --ff-only
git log -1 --oneline
sudo ./upgrade.sh
sudo androidctl fleet setup
```

If Git reports local changes or divergent history, preserve/reconcile those
changes before continuing; do not reset the checkout blindly.

For a **fresh host**, use this instead of the upgrade commands:

```bash
git clone https://github.com/darkmatter2222/AndroidCtl.git
cd AndroidCtl
sudo ./install.sh
sudo androidctl doctor
sudo androidctl fleet setup
```

Review/accept the SDK licenses when prompted. Fleet setup defaults to API 35,
preserves existing userdata, backs up edited configuration, creates missing
devices, and raises the concurrency limit to at least four. All managed
instances must be stopped. Existing incompatible API/profile configurations
cause a refusal rather than replacement. Do not run the separate mixed-version
single-device example below if you want this four-device API 35 fleet.

Setup selects **SwANGLE with guest Vulkan disabled**, the workaround that
initially succeeded after RenderThread SIGSEGV failures with software/SwiftShader.
This is not a guarantee of four-device stability; validate the real workload.
It uses software rendering, not the NVIDIA GPU. Default new-device allocations
total 16 GiB guest RAM across four devices, plus host/renderer overhead.

Setup preserves the saved bind address. For LAN screen access, while devices
are still stopped, select your private interface if not already configured:

```bash
sudo androidctl config set bind_address auto
```

### Start and manage the fleet

```bash
sudo androidctl fleet start
sudo androidctl fleet watch
```

Start queues the four systemd services and returns before boot finishes.
Press **Ctrl+C** to leave the watcher, then inspect readiness:

```bash
sudo androidctl fleet status
```

**Closing SSH or the watcher leaves devices running.** No tmux/nohup is needed.
Host reboot is separate: opt into boot startup with `sudo androidctl fleet enable`.

| Action | Command |
|---|---|
| List/count devices, health, endpoints, and restarts | `sudo androidctl fleet status` |
| Start all four (safe when already active) | `sudo androidctl fleet start` |
| Stop all four | `sudo androidctl fleet stop` |
| Start selected devices | `sudo androidctl fleet start 1 3` |
| Stop device 2 | `sudo androidctl fleet stop 2` |
| Restart device 2 | `sudo androidctl fleet restart 2` |
| Start all at host boot | `sudo androidctl fleet enable` |
| Disable boot startup | `sudo androidctl fleet disable` |
| Print actual screen connection commands | `androidctl fleet screen` |
| Print device 1 screen commands | `androidctl fleet screen 1` |
| Follow fleet state log | `sudo androidctl fleet watch` |
| Follow device 1 emulator logs | `sudo androidctl logs 01 --follow` |

Fleet start/stop/restart are asynchronous; check status for completion.
For a synchronous stop before an upgrade/setup, use the systemctl commands above.
Disabling boot startup does not stop currently running devices.

### Open screens from Windows

Run `androidctl fleet screen` over SSH, then execute the printed commands on
Windows where ADB and scrcpy are installed. For device 1 (replace
`<ANDROID_HOST>` with the reported private host address):

```cmd
adb disconnect <ANDROID_HOST>:15551
adb connect <ANDROID_HOST>:15551
scrcpy -s <ANDROID_HOST>:15551 --no-audio --video-codec=h264 --max-fps=30 --print-fps
```

Devices 2–4 normally use 15552, 15553, and 15554; saved overrides take precedence.
Use separate Windows terminals for simultaneous windows. Omitting `--max-size`
avoids a capture downscale; resizing a desktop window does not change Android's
native resolution. See the LAN access/security notes below.

Verify all four native displays after boot:

```bash
for id in 01 02 03 04; do
    echo "Device $id"
    androidctl adb "$id" shell wm size
    androidctl adb "$id" shell wm density
done
```

Expect physical size 1344×2992, physical density 480, and no overrides.

### Persistent monitoring and crash recovery

Setup enables and starts `android-fleet-monitor.service`. It samples every
10 seconds, records state changes and 60-second heartbeats, and writes to
`/var/log/androidctl/fleet.jsonl` (or the configured log root). Logs rotate at
5 MiB with five backups. Records include UTC time, ID, PID, state/substate,
restart count, result, exit status, proxy state, and remote port.

```bash
sudo tail -n 50 /var/log/androidctl/fleet.jsonl
sudo systemctl status android-fleet-monitor.service
sudo androidctl fleet watch
```

The monitor observes; it does not resurrect intentionally stopped devices or
automatically recover a frozen guest. systemd restarts crashed emulator processes,
with a three-start/five-minute limit. Polling can miss brief transitions, so use
per-device journals for the full crash history. A healthy result after a restart
does not erase earlier crashes; compare PIDs and restart counts.

To stop monitoring independently:
`sudo systemctl disable --now android-fleet-monitor.service`.
Devices continue running. Validate all four under load, disconnect/reconnect SSH,
and check restarts and logs before relying on unattended operation.

Further details and rollback: [four-device fleet guide](docs/fleet.md).

## Requirements

- Ubuntu **24.04 LTS**, x86_64, systemd, firmware virtualization enabled, working `/dev/kvm`.
- Root access for installation and lifecycle/config changes. Emulators run as an unprivileged service account.
- RAM for each device plus a host reserve. Defaults: 4 GB/device, 4 CPU cores, maximum two simultaneous devices before fleet setup raises the limit to at least four, 4 GB host RAM reserve.
- Free storage for SDK images and growing persistent userdata; default virtual data partition is 16 GB/device.
- Internet access to Google's SDK downloads and Ubuntu package repositories; acceptance of Google's SDK licenses.
- No desktop or Android Studio required. Software graphics is the initial default. Physical Mesa GPU use requires explicit selection.

## Install

```bash
git clone https://github.com/darkmatter2222/AndroidCtl.git
cd AndroidCtl
sudo ./install.sh
sudo androidctl doctor
androidctl profiles
```

The installer reviews SDK licenses interactively. For an administrator who has already reviewed and accepted them, `sudo ./install.sh --accept-licenses` supplies acceptance noninteractively. `--user <SERVICE_USER>` selects an existing non-root account or creates a dedicated one; the default account is `androidctl`.

A pinned, official command-line-tools ZIP is SHA-256 verified. The installer installs Java 21, the emulator, platform-tools, graphics libraries, and socat. It preserves existing instance configs and AVDs. BIOS changes, reboots, driver replacement, firewall changes, and Docker changes are never performed. [Installation details](docs/installation.md).

## First device and another Android version

```bash
sudo androidctl create 01 --api 35 --profile pixel_8_pro --install-image
sudo androidctl start 01
androidctl list
androidctl status 01

sudo androidctl create 02 --api 34 --profile pixel_8_pro --install-image
sudo androidctl start 02
androidctl list --json
```

`pixel_8_pro` must appear in `androidctl profiles`. If it is unavailable, choose an actual listed profile or update the tools. The manager never silently substitutes a different device. `androidctl sdk images` lists available x86_64 variants; a Play Store image is used only when actually available. Images for different API levels coexist.

The official profile specifies emulator characteristics. It does **not** reproduce Pixel Tensor hardware, modem/baseband, secure hardware, hardware-backed attestation, certification, or Play Integrity. A logical instance ID is not an IMEI, Android ID, advertising ID, or secure hardware identity.

## Static ports

| ID | Console (loopback) | Local ADB | Remote/proxy ADB |
|---|---:|---:|---:|
| 01 | 5554 | 5555 | 15551 |
| 02 | 5556 | 5557 | 15552 |
| 03 | 5558 | 5559 | 15553 |
| 04 | 5560 | 5561 | 15554 |
| 10 | 5572 | 5573 | 15560 |

Console = `5554 + 2 × (ID − 1)`; local ADB = console + 1; proxy = `15550 + ID`. Ports are saved at creation, checked against every configured device and existing listeners, and never reassigned automatically. Supported console ports are even values from 5554 through 5682. Advanced overrides and range details: [ports](docs/ports.md).

## Connect from Windows with ADB and scrcpy

By default, the proxy binds **127.0.0.1 only**. To opt into the host's primary private LAN address, stop all managed devices first:

```bash
sudo systemctl stop 'android-emulator@*.service'
sudo systemctl stop 'android-adb-proxy@*.service'
sudo androidctl config set bind_address auto
sudo androidctl start 01
androidctl adb-endpoint 01
```

`start` reports the selected address. A fixed private interface address can be configured instead of `auto`. Replace `<ANDROID_HOST>` with the reported host address/name on your trusted LAN:

```cmd
adb connect <ANDROID_HOST>:15551
adb devices
scrcpy -s <ANDROID_HOST>:15551
```

For the second running device:

```cmd
adb connect <ANDROID_HOST>:15552
scrcpy -s <ANDROID_HOST>:15552
```

If audio initialization fails, use `scrcpy -s <ANDROID_HOST>:15551 --no-audio`. Codec availability depends on the client, Android image, and encoder; use `scrcpy --help` / `--list-encoders` before selecting one. [Remote ADB and SSH tunneling](docs/remote-adb.md).

**ADB is a privileged management interface.** The proxy adds no authentication or encryption. Use an administrator-controlled LAN/firewall/VPN or an SSH tunnel. Never forward these ports from the internet. AndroidCtl does not open firewall rules.

## Daily operations

```bash
sudo androidctl stop 01
sudo androidctl restart 01
sudo androidctl enable 01       # opt in to boot-time startup
sudo androidctl disable 01      # disable boot-time startup; does not stop it
androidctl logs 01 --follow
androidctl logs 01 --since 10m
androidctl shell 01
androidctl adb 01 shell getprop ro.build.version.release
androidctl health 01 --json
androidctl ports
androidctl info 01
```

Read-only CLI commands normally need no sudo. Journal access may require sudo or membership in your host's journal-reader group. The managed ADB server is loopback-only on port 5038, separate from the usual port 5037.

Shutdown requests Android filesystem sync and emulator exit, waits, then escalates to SIGTERM and finally systemd's SIGKILL only if necessary. Forced termination is reported in the journal. An intentional systemd stop does not trigger crash restart. Crashes are limited to three starts within five minutes.

## Persistence and backups

Each AVD lives under `/var/lib/androidctl/avd/<NAME>.avd`; the corresponding `.ini` pointer is beside it. Configuration lives under `/etc/androidctl/instances/<ID>.conf`.

Start, stop, restart, reboot, and manager upgrades preserve userdata. Normal launch has no wipe flag. Automatic snapshot loading/saving is disabled, so userdata is the persistence mechanism.

Back up **stopped** AVD directories, their pointers, and instance configuration together. Preserve ownership, sparse files, and exact paths. [Backup/restore procedure](docs/persistence.md). Snapshot, clone, and automated backup/restore commands are deliberately not shipped in v1.

## GPU selection and KVM

```bash
androidctl gpu list --json
sudo androidctl create 03 --api 35 --profile pixel_8_pro --install-image \
  --gpu host --gpu-pci <PCI_ADDRESS_FROM_GPU_LIST>
```

For Mesa drivers, a stable global selector is also supported:

```bash
sudo androidctl config set dri_prime <MESA_PCI_SELECTOR>
```

Use the `pci-` form described in [GPU configuration](docs/gpu.md). Defaults apply to newly created instances. Hardware/auto modes require an explicit selection. The selected device's nodes are the only GPU nodes allowed by the emulator's systemd device policy. Proprietary NVIDIA selection is not supported in v1; software rendering leaves physical accelerators unassigned.

Software modes include `software`, `swiftshader`, `lavapipe`, and `swangle`; availability depends on your emulator version. The deprecated `swiftshader_indirect` name is accepted for older installations. A failed renderer is reported; no other physical GPU is silently selected.

`sudo androidctl doctor --json` checks virtualization flags, KVM modules/device, service group, emulator acceleration, SDK tools, Java, systemd, GPU inventory, EGL/GLX diagnostics, paths, and bind address. A headless GLX warning alone is not a KVM failure. [Troubleshooting](docs/troubleshooting.md).

## Resources and autostart

Devices are stopped and autostart-disabled when created unless `--start` is requested. Resource admission is enforced by the systemd preflight too, covering host boot and direct service starts. A global lock and reservations serialize admission of simultaneously booting instances. `androidctl start ID --force` overrides RAM/concurrency/CPU admission only; it does not bypass KVM, port, or GPU requirements.

## Architecture and configuration

`androidctl` → validated INI configuration → systemd per-instance services → official emulator/KVM → private AVD userdata. A dedicated ADB service manages local transports; a per-instance socat proxy starts after Android boot and postboot settings complete.

- `src/androidctl/`: CLI, config, ports, SDK/AVD adapters, lifecycle, GPU, diagnostics, health, service helpers.
- `systemd/`: emulator/proxy templates and dedicated ADB server.
- `scripts/deploy.py`, `install.sh`, `upgrade.sh`, `uninstall.sh`: host deployment.
- `config/`: portable example configurations.
- `tests/`, `.github/workflows/ci.yml`: hardware-independent checks.
- `docs/`: operational procedures, references, acceptance checks, and security.

Global file: `/etc/androidctl/androidctl.conf`. Inspect with `androidctl config show`. Existing instances retain their own saved ports, CPU, RAM, image, and GPU. See [architecture](docs/architecture.md) and [command reference / exit codes](docs/instances.md).

## Upgrade and uninstall

```bash
# Stop all managed devices first.
git pull --ff-only
sudo ./upgrade.sh
```

Manager upgrades preserve configuration and AVD data and do not update the SDK. `sudo androidctl sdk update` is a separate, offline operation. Back up first. [Upgrade and rollback](docs/upgrading.md).

```bash
sudo ./uninstall.sh                # preserve all device data/configuration
sudo ./uninstall.sh --purge        # explicitly confirm deletion of registered AVDs/configs
```

Uninstall refuses while devices are active. Purge deliberately retains the SDK, service account/home, unregistered preserved AVDs, and unrelated files; inspect and remove those separately if desired. It never recursively deletes an arbitrary configured root directory.

## Development

[![CI](https://github.com/darkmatter2222/AndroidCtl/actions/workflows/ci.yml/badge.svg)](https://github.com/darkmatter2222/AndroidCtl/actions/workflows/ci.yml)

CI runs unit tests on Python 3.10, 3.12, and 3.13, plus Ruff lint/format checks,
ShellCheck, systemd unit validation, and CLI help checks. The 55-test suite passed
on all three versions in [run 37857561497](https://github.com/darkmatter2222/AndroidCtl/actions/runs/37857561497).
Commit `039c3d3` fixed a fleet test that incorrectly depended on a root test runner
and added a separate non-root rejection test. Follow the badge for current status.
These checks do not validate KVM, graphics stability, or four-device host performance.

No third-party runtime dependencies or Python virtualenv required:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m ruff check src scripts tests
python3 -m ruff format --check src scripts tests
shellcheck install.sh upgrade.sh uninstall.sh scripts/*.sh
python3 scripts/validate_units.py
```

Development lint tools are pinned in `requirements-dev.txt`. Hardware tests are opt-in; see [validation](docs/validation.md). Report bugs without uploading keys, personal host details, userdata, or unredacted logs. [Security policy](SECURITY.md), [contributing](CONTRIBUTING.md), [official tooling sources](docs/sources.md).
