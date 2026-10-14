# OpenCode 2.x AndroidCtl plugin

## Install by asking your agent

Give OpenCode this instruction (replace the placeholders):

> Install the OpenCode 2.x plugin from https://github.com/darkmatter2222/AndroidCtl. Read docs/opencode.md, check out branch `feat/opencode-androidctl`, and run `node opencode/install.mjs --host MY_ANDROID_HOST --ssh MY_SSH_USER@MY_ANDROID_HOST` on this desktop. Preserve existing OpenCode settings and androidctl.json. Check adb and scrcpy availability. Use the host's saved endpoints if ports differ. Tell me when to restart OpenCode.

This installs a local plugin, not an npm-published package. Requirements: OpenCode **2.x**, Node **22+**, and `adb` plus `scrcpy` on the desktop that will show the windows. SSH is needed only for host management. No build step, npm install, cloud account or model is required for viewer/lifecycle commands. The OpenCode runtime provides `@opencode/plugin`. Version 1.x hooks/config are not supported. The adapter was type-checked and smoke-tested against the published `@opencode/plugin` 2.0.29 SDK.

Manual installation from a checkout:

```sh
git clone --branch feat/opencode-androidctl https://github.com/darkmatter2222/AndroidCtl.git
cd AndroidCtl
node opencode/install.mjs --host YOUR_ANDROID_HOST --ssh YOUR_USER@YOUR_ANDROID_HOST
```

The same command works from PowerShell, Command Prompt and a Linux/macOS shell. Windows must have Node, ADB and scrcpy installed and on PATH (or configured by absolute executable path). Test `adb version` and `scrcpy --version`. Linux needs a graphical desktop session; headless SSH cannot display a local Windows window. With a remote OpenCode server, plugin processes run on that server. Install/run OpenCode on your desktop for desktop windows.

Restart OpenCode after installation; try `/androidctl help`, then `/androidctl A`.

The installer writes `~/.config/opencode/plugins/androidctl/` and `~/.config/opencode/androidctl.json` (`XDG_CONFIG_HOME` supported). On Windows, `~` means your user home, e.g. `C:\Users\ryans`. It does not overwrite existing client configuration or edit your OpenCode JSON/JSONC. Existing plugin directories cause an explicit refusal, not replacement. If using a nonstandard OpenCode config directory, pass `--config-dir PATH`. Set `ANDROIDCTL_CONFIG` to the full JSON path if it is outside the default location.

OpenCode 2.x also supports installing Git subdirectory packages directly:

```sh
opencode plugin add 'github:darkmatter2222/AndroidCtl#feat/opencode-androidctl::path:opencode/androidctl'
```

Use double quotes instead of single quotes in Windows Command Prompt. This installs the plugin only: copy `opencode/androidctl/androidctl.example.json` to `~/.config/opencode/androidctl.json` and set your host. Once this branch is merged, use `#main` instead, or pin a reviewed commit hash. Do not combine this with the local installer.

Alternatively keep the plugin in a checkout and add its absolute directory to the OpenCode 2.x `plugins` array (merge with existing entries):

```json
{ "plugins": ["C:/Users/you/source/repos/AndroidCtl/opencode/androidctl"] }
```

Use exactly one loading method to avoid duplicate registrations.

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

Direct commands execute without a model turn and report via a synthetic session message. Guided `deploy`, `debug`, and `mcp` commands use your current agent and its tools/model/permissions. They are not automatic unattended installers or a new autonomous agent team. See [operator runbook](../opencode/androidctl/OPERATIONS.md).

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

Configuration is read on each direct command, so edits need no restart. Uppercase aliases can be extended beyond A–D. IDs are the host lifecycle IDs, not ADB serials. Override a device with `"endpoint": "other-host:16662"` instead of `port`; this also supports tunnel endpoints such as `127.0.0.1:15551` and bracketed IPv6. Explicit endpoint strings take precedence over `host`/`port`. Viewing may span multiple hosts, but **all lifecycle commands use the single management.target**, so only configure lifecycle IDs for that host.

The host already persists ports under `/etc/androidctl/instances/`. Client defaults 15551–15554 are conveniences, not discovery. Run `androidctl fleet screen` on the host or `/androidctl endpoints all`, then copy the reachable saved endpoints into client configuration. Host-reported loopback/bind addresses may not be directly reachable from your desktop.

Optional management keys: `port` (SSH port number) and `identityFile` (path to an SSH key, not its contents). Executable values accept absolute paths including spaces; Windows JSON backslashes must be doubled. No shell command fragments are accepted in the slash command. SSH uses normal host-key verification, `BatchMode=yes`, and a 10-second connection timeout; configure/test SSH interactively first. Mutations and doctor use `sudo -n`, which fails clearly if privilege is unavailable. Configure only narrowly scoped administrator-approved sudo access if needed, or perform privileged steps interactively. The plugin never installs sudoers rules or saves passwords. Journal access may require a journal-reader group.

Viewer flags mirror the original recipe: no audio, H.264, maximum 30 FPS (configurable), FPS logging, and a distinct window title. No `--max-size` is applied, so the plugin does not downscale capture or alter Android's native display. FPS is a cap, not a performance guarantee.

Viewer stdout/stderr is saved under `~/.local/state/androidctl/viewer/` (`XDG_STATE_HOME` supported). The response includes the log path and PID. Startup checks catch missing executables and immediate failures; a launched process does not prove sustained video delivery. Old logs are not automatically rotated; remove them when no longer needed. Host commands have a 45-second client timeout and 2 MiB output cap. A timeout does not cancel a remote operation already submitted: inspect status before retrying.

## Update, remove, and test

Update the checkout with `git pull --ff-only`. Back up/remove only the installed `plugins/androidctl` directory, then rerun the installer; it retains `androidctl.json`. Restart OpenCode. Remove that same directory to uninstall; remove any manually added `plugins` entry if you used one. Neither action stops VMs or removes AVDs. Already-open scrcpy windows stay open until closed.

Standalone smoke test without OpenCode (same config):

```sh
node opencode/androidctl/cli.mjs help
node opencode/androidctl/cli.mjs A,B
node --test opencode/androidctl/test/*.test.mjs
```

Automated tests cover argument safety, exact endpoint routing, partial failures, management routing and installation preservation. Live Windows GUI launch, SSH privilege setup and an actual OpenCode 2.x session require acceptance testing on the desktop. Test A first, then all four; confirm window titles, no unselected endpoint disconnects, native resolution, bounded logs, and failed-host messages. Existing Python tests remain unchanged.

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

API reference used: [OpenCode 2.x plugin commands and sessions](https://dev.opencode.ai/v2/docs/build/plugins/). This integration uses `@opencode/plugin`, `Plugin.define`, command transforms, `session.synthetic`, and `session.prompt`; it does not use the OpenCode 1.x `command.execute.before` interception workaround.
