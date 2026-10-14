# OpenCode 2.x AndroidCtl plugin

## Install and update (managed package)

OpenCode **2.x** (SDK checked against 2.0.29), Node **22+**, ADB and scrcpy are required. Install on the desktop where the windows should appear. The viewer now runs in the terminal client, including when connected to a remote OpenCode server. A graphical desktop is required; a headless terminal cannot open a desktop window.

From a current checkout of this repository:

```sh
git switch main
git pull --ff-only
node opencode/install.mjs --host YOUR_ANDROID_HOST --ssh YOUR_USER@YOUR_ANDROID_HOST
```

The default installer uses OpenCode's native package manager and remembers this moving source:

```text
github:darkmatter2222/AndroidCtl#main::path:opencode/androidctl
```

Existing `androidctl.json` is preserved. The old copied `~/.config/opencode/plugins/androidctl` folder is moved to `~/.config/opencode/androidctl-backups/` after successful installation, and the old `feat/opencode-androidctl` package subscription is removed if present. Other plugins are untouched. If you manually configured a local checkout path, remove that old entry as well so only one AndroidCtl package is loaded. Restart OpenCode once after migration to unload the old server-side command.

**Existing 0.1.0 copied installs require this one-time migration.** A local folder has no package subscription, so `/plugins` cannot download its first update. After migration, no URL needs to be supplied again.

### Normal updates

1. Open **`/plugins`** (plural).
2. Use **check for updates** (`Ctrl+R` in the current OpenCode defaults).
3. Select **androidctl under Server** and choose **update** when available. The package's terminal component updates with it; the separate `androidctl.tui` entry is for enable/disable controls.

Equivalent terminal commands, with no URL:

```sh
opencode plugin check
opencode plugin update
```

The updater tracks the moving `main` Git revision. GitHub release tags provide versioned downloads, while the package subscription provides update detection. Pinning an exact commit/tag freezes that revision; local copies are skipped by native updates. If a merge happened after OpenCode started, explicitly check rather than relying on the cached startup result. Restart if the old command remains loaded.

For a fresh package-only install without the helper:

```sh
opencode plugin add "github:darkmatter2222/AndroidCtl#main::path:opencode/androidctl"
```

Copy `opencode/androidctl/androidctl.example.json` to `~/.config/opencode/androidctl.json` and set your host. `~` is your user home (`C:\Users\ryans` on Ryan's Windows desktop); `XDG_CONFIG_HOME` and `ANDROIDCTL_CONFIG` overrides are supported. Executables must be on PATH or configured with absolute paths. Check `adb version` and `scrcpy --version`.

For offline/local development only, `node opencode/install.mjs --local [--config-dir PATH]` still copies the package. That mode deliberately has no native update subscription. OpenCode's global managed installation uses its own global config directory; `--config-dir` is only accepted with `--local`.

## Commands

| OpenCode command | Behavior |
|---|---|
| `/androidctl A` | Disconnect/reconnect A's exact ADB endpoint, check readiness, open scrcpy |
| `/androidctl A,B,C,D` | Open four independent windows; failures reported per device |
| `/androidctl all` | View all configured aliases |
| `/androidctl view B,D` | Explicit viewer form |
| `/androidctl 192.168.86.48:15551` | View a direct endpoint without adding an alias |
| `/androidctl list` | List all devices on the configured SSH host as JSON |
| `/androidctl status` | Detailed state for all configured aliases |
| `/androidctl health B` | Health/boot/proxy checks for B |
| `/androidctl start A,B` | Start selected VMs |
| `/androidctl stop B,C,D` | Stop selected VMs, preserving userdata |
| `/androidctl restart A` | Restart A; coordinate with its automation owner |
| `/androidctl enable all` | Enable boot-time startup |
| `/androidctl disable all` | Disable boot startup; does not stop active VMs |
| `/androidctl logs C` | Previous 10 minutes of emulator/proxy journals |
| `/androidctl ports` | Host's saved port assignments |
| `/androidctl endpoints all` | Print host-reported endpoints; does not silently rewrite client config |
| `/androidctl doctor` | Host diagnostics, using noninteractive sudo |
| `/androidctl config` | Show client config and its path |
| `/androidctl deploy …` | Ask the current agent to follow the deployment runbook |
| `/androidctl debug …` | Ask the current agent to investigate symptoms using evidence |
| `/androidctl mcp …` | Ask the agent to set up the partner automation/MCP project |

Direct commands are terminal UI commands: viewer success uses a toast; help, status, logs, configuration and failures use dialogs. They never submit a session prompt, synthetic message, or model request and never add their output to chat context. Guided `deploy`, `debug`, and `mcp` commands use your current agent and its tools/model/permissions. They are not automatic unattended installers or a new autonomous agent team. See [operator runbook](../opencode/androidctl/OPERATIONS.md).

No implicit start happens when viewing a stopped VM. Lifecycle completion is asynchronous; run `status`/`health` after start, stop, or restart. Selecting `all` means configured aliases for per-device commands; `list` and `ports` inspect the whole SSH host. Multiple viewers are allowed; repeated commands open additional windows. Closing a viewer does not stop its VM. Reconnecting ADB can interrupt an automation session on that endpoint; coordinate with the device owner.

## Configuration

Example for Ryan's four devices (this private address is an example, never a shipped default):

```json
{
  "host": "192.168.86.48",
  "adb": "adb",
  "scrcpy": "scrcpy",
  "ssh": "ssh",
  "maxFps": 30,
  "devices": {
    "A": { "id": "01", "port": 15551 },
    "B": { "id": "02", "port": 15552 },
    "C": { "id": "03", "port": 15553 },
    "D": { "id": "04", "port": 15554 }
  },
  "management": { "target": "YOUR_USER@192.168.86.48" }
}
```

Configuration is read locally by the terminal client on each direct command, so edits need no restart. Uppercase aliases can be extended beyond A–D. IDs are the host lifecycle IDs, not ADB serials. Override a device with `"endpoint": "other-host:16662"` instead of `port`; this also supports tunnel endpoints such as `127.0.0.1:15551` and bracketed IPv6. Explicit endpoint strings take precedence over `host`/`port`. Viewing may span multiple hosts, but **all lifecycle commands use the single management.target**, so only configure lifecycle IDs for that host.

The host already persists ports under `/etc/androidctl/instances/`. Client defaults 15551–15554 are conveniences, not discovery. Run `androidctl fleet screen` on the host or `/androidctl endpoints all`, then copy the reachable saved endpoints into client configuration. Host-reported loopback/bind addresses may not be directly reachable from your desktop.

Optional management keys: `port` (SSH port number) and `identityFile` (path to an SSH key, not its contents). Executable values accept absolute paths including spaces; Windows JSON backslashes must be doubled. No shell command fragments are accepted in the slash command. SSH uses normal host-key verification, `BatchMode=yes`, and a 10-second connection timeout; configure/test SSH interactively first. Mutations and doctor use `sudo -n`, which fails clearly if privilege is unavailable. Configure only narrowly scoped administrator-approved sudo access if needed, or perform privileged steps interactively. The plugin never installs sudoers rules or saves passwords. Journal access may require a journal-reader group.

Viewer flags mirror the original recipe: no audio, H.264, maximum 30 FPS (configurable), FPS logging, and a distinct window title. No `--max-size` is applied, so the plugin does not downscale capture or alter Android's native display. FPS is a cap, not a performance guarantee.

Viewer stdout/stderr is saved under `~/.local/state/androidctl/viewer/` (`XDG_STATE_HOME` supported). The response includes the log path and PID. Startup checks catch missing executables and immediate failures; a launched process does not prove sustained video delivery. Old logs are not automatically rotated; remove them when no longer needed. Host commands have a 45-second client timeout and 2 MiB output cap. A timeout does not cancel a remote operation already submitted: inspect status before retrying.

## Update, remove, and test

Use `/plugins` as described above for updates. Uninstall a managed package with:

```sh
opencode plugin remove "github:darkmatter2222/AndroidCtl#main::path:opencode/androidctl"
```

Remove any leftover explicitly configured local entry separately. Keep `androidctl.json` if you plan to reinstall. No uninstall step stops VMs, removes AVDs or closes existing scrcpy windows.

Standalone smoke test without OpenCode (same config):

```sh
node opencode/androidctl/cli.mjs help
node opencode/androidctl/cli.mjs A,B
node --test opencode/androidctl/test/*.test.mjs
```

Automated tests cover argument safety, exact endpoint routing, partial failures, management routing, installation preservation, one-time managed migration, duplicate in-flight submissions and zero client/session API access for direct commands. Live Windows GUI launch, SSH privilege setup and an actual OpenCode 2.x session require acceptance testing on the desktop. Test A first, then all four; confirm window titles, no unselected endpoint disconnects, native resolution, bounded logs, and failed-host messages. Existing Python tests remain unchanged.

## Extension ideas / roadmap (not shipped)

Prioritized possibilities, kept separate from implemented commands:

| Area | Ideas |
|---|---|
| Viewer | Focus existing window; configurable window layout; tiled fleet view; read-only scrcpy mode; recording; screenshot capture; per-device FPS/codec profiles |
| Fleet visibility | Live status panel; boot progress; crash/restart timeline; resource charts; proxy reachability map; saved inventory import; multiple management hosts |
| Deployment | Versioned deployment plans; prerequisite audit report; capacity planner; reviewed upgrade/rollback workflow; SSH tunnel provisioning; endpoint discovery wizard |
| Diagnosis | Crash signature classification; redacted diagnostic bundles; before/after health diff; renderer comparison; ADB outage timeline; explicit repair plans |
| Lifecycle/data | Maintenance windows; coordinated worker pause/resume; stopped-device backups; backup verification; restore rehearsals; controlled cloning when host support exists |
| Automation | Partner MCP setup validation; worker ownership display; benchmark launcher; benchmark comparisons; reusable task presets; MasterGoal handoff; evidence browser |
| Quality | OpenCode runtime integration tests; real Windows/macOS/Linux viewer matrix; KVM acceptance runner; configuration schema/editor; installer upgrade migration; signed releases |

These are future features, not commands users can invoke today. Device deletion, arbitrary remote shell execution, silent repairs, image replacement, and automatic SDK license acceptance are intentionally outside the direct command surface.

API reference used: [OpenCode 2.x plugin commands and sessions](https://dev.opencode.ai/v2/docs/build/plugins/). The terminal entrypoint uses `@opencode/plugin/tui`, a slash command in a keymap layer, and transient UI dialogs/toasts. The server entrypoint is intentionally inert. Only explicit deploy/debug/MCP workflows call `session.prompt`. No code calls `session.synthetic`. See also [terminal plugin API](https://dev.opencode.ai/v2/docs/build/plugins/cli) and [native plugin updates](https://dev.opencode.ai/v2/docs/plugins).
