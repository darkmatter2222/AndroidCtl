# Commands, configuration, and exit codes

Run `androidctl --help` or `<command> --help` for flags. Global `--config PATH` must precede the command; systemd always reads the installed `/etc/androidctl/androidctl.conf`.

| Command | Purpose |
|---|---|
| `create ID --api N --profile PROFILE --install-image` | Create stopped persistent AVD; install missing available image |
| `create ID --start` | Create then start |
| `start ID [--force]`, `stop ID`, `restart ID [--force]` | Manage lifecycle; force overrides capacity only |
| `list [--json]`, `status [ID] [--json]` | All devices or detailed device state |
| `info ID`, `health ID [--json]` | Detailed metadata or health with failure exit status |
| `ports [--json]`, `adb-endpoint ID` | Permanent ports and actual proxy endpoint |
| `enable ID`, `disable ID` | Toggle boot-time startup |
| `logs ID [--follow] [--since 10m]` | Both emulator and proxy journal |
| `shell ID`, `adb ID ARGS...` | Interactive Android shell / arbitrary ADB command |
| `profiles [--json]`, `gpu list [--json]` | Actual installed profiles / host GPU inventory |
| `sdk status`, `sdk images` | Selected tooling and available x86_64 images |
| `sdk install-image --api N [--image VARIANT]` | Install a discovered image |
| `sdk licenses [--accept]`, `sdk update` | Review licenses / offline package updates |
| `config show`, `config get KEY`, `config set KEY VALUE` | Global defaults and policy |
| `doctor [--json]`, `version` | Diagnostics and manager version |
| `delete ID [--yes] [--keep-data]` | Stop, unregister, and optionally erase AVD |

Creation accepts `--ram` (MB), `--cpus`, `--disk` (`16G`, `8192M`), `--name`, `--gpu`, `--gpu-pci`, `--console-port`, `--remote-adb-port`, `--image`, and `--architecture`. Architecture is currently restricted to x86_64. Missing profile/image fails with an actionable error.

Global defaults are copied into newly created instance configurations; changing them does not silently rewrite existing devices. Stop a device before editing its saved instance configuration manually. Keep ID, name, profile/image and paths consistent with its AVD. Disk resizing, image replacement, and renaming existing devices are not supported mutations: create a separate device and migrate deliberately. Editing a RAM/CPU/GPU selection is supported while stopped; next CLI start regenerates its device policy. After editing GPU settings for boot-time startup, run `upgrade.sh` while all devices are stopped to regenerate policies.

Path/service identity and unit timeout settings require editing the config offline and running `upgrade.sh`; path changes additionally require explicit data migration. Changing the ADB server port requires restarting `android-adb.service` while all devices are stopped. Configuration saves are atomic. SDK operations and mutations require root.

## State and health

States: stopped, starting, booting, running, stopping, failed, unknown. Health: healthy, degraded, unhealthy, unknown. The boot property must equal `1`; process existence alone is insufficient. An Android guest can be booted while its proxy is failed, yielding running/degraded. `active_since` reports the systemd active timestamp; `pid`, Android release, resource settings and persistent AVD path are included in detailed output.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Success |
| 2 | Invalid arguments or configuration |
| 3 | Instance/configuration missing |
| 4 | Duplicate instance/name or already transitioning/running |
| 5 | Host prerequisite, permission, dependency, or command failure |
| 6 | Static port collision/unavailable bind |
| 7 | CPU/RAM/concurrency/storage capacity rejection |
| 8 | Profile/system image unavailable or installation declined |
| 9 | Start/stop/boot timeout or failed systemd lifecycle |
| 10 | Health check not healthy |
| 11 | Destructive operation refused |
| 130 | Interrupted |

Internal helper failures are recorded with their specific code in journald; the outer asynchronous start command reports code 9 for a failed systemd job. `adb` and `logs` propagate the underlying command exit code.
