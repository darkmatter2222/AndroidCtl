# AndroidCtl management console

The catalog models an instance as a persistent reservation: server + instance ID,
AVD storage, Android image, hardware configuration, default resolution, and stable
public ADB port. Running Android is a state of that reservation. Stopping or power
cycling it never calls create and does not remove its storage.

## Launch and update

Requires Python 3.10+, ADB, and optionally native scrcpy on the controller.
Run start-web.bat on Windows or ./start-web.sh on Linux/macOS from the checkout.
Installed alternatives are androidctl-web and python -m androidctl.web. Linux also
supports androidctl web. No Node build or third-party Python runtime dependency.

Options include --port, --adb, --scrcpy, --adb-port, --state, and --no-browser.
Port 8765 is preferred; if the default is blocked or occupied the OS chooses an
available port. Explicit ports are honored. --port 0 always selects a free port.
Desktop ADB defaults to 5037; the managed Linux host's ADB server uses 5038.

Pull updates on the controller and upgrade AndroidCtl on each Linux host before
creating catalog reservations. upgrade.sh requires existing emulators to be stopped.
Upgrade retains AVD storage and registered instance configurations.

The browser URL includes a per-process token. Reopen the printed URL after restarting
the server. Tokens are held in session storage, removed from the URL, and required
for API requests. The web server binds only 127.0.0.1 and validates Host and Origin.
Use a normal desktop account, not root. Ctrl+C stops the web service, not Android.

## Server connection and inventory

Add server asks separately for a label, server IP/hostname, SSH username and SSH
port. The server list displays both the actual SSH target and the ADB host address.
SSH key authentication and an already verified host key are required. Lifecycle
operations run sudo -n androidctl; configure suitable noninteractive sudo access
on the host. The app never accepts arbitrary shell commands, edits sudoers, or
silently trusts SSH host keys. Connection help shows terminal checks for the
actual saved target. SSH aliases and local profiles already saved through the API
remain supported, though the wizard creates explicit user@host targets.

The first host-list request automatically scans saved servers once per web process.
Refresh server or Scan instances updates changes made outside the app. The light
androidctl inventory --json command reads configuration and systemd state without
guest ADB calls. Older servers fall back to list --json only if inventory is an
unsupported command. Scans have a 90-second command deadline.

Successful inventory persists in web-hosts-inventory.json alongside web-hosts.json.
It is bound to the exact saved server profile. Failed scans keep previous rows and
show their timestamp and stale status. “Inventory unavailable” is distinct from a
successfully scanned server with no registered instances. Actual errors are shown:
SSH login, host-key, command availability and malformed-output errors are not all
reported as an incorrect IP address.

## Object navigation

The resizable Explorer is the primary navigation. Connections is the root view.
Local controller contains unmanaged USB/local ADB and saved network devices.
Each remote server contains all registered Android instances, including stopped
ones. A USB device attached to the controller never belongs to a remote server.
Search the tree by server, instance name/ID/state/port or device identity. Use
arrow keys to move/expand/collapse and Enter to select. Breadcrumbs return to parents.

Actions are scoped to the selected object:

- Connections: Add server and refresh.
- Local controller: Scan ADB and add a network device.
- Server: Scan instances, Create instance, Edit connection, Remove connection.
- Instance: Start, Stop, Power cycle, Delete instance and refresh.
- Controller device: Connect, Disconnect, Edit name and Remove saved connection.

There is no global Create instance action. Creation is bound to the selected
server and requires verified inventory. Editing retains the server identifier.
Removing a connection only removes the controller profile and its inventory cache;
it does not run a remote command or delete Android data. Attached USB devices
remain discoverable after removing a saved connection.

Server tabs separate Instances, Connection, Diagnostics and Console. Instance tabs
separate Summary, Configuration and Console. Each Console shows only devices owned
by the selected object. Opening a console is explicit; neither inventory discovery
nor selecting a tree node starts screenshot capture. The bottom operations pane
shows the latest operation per server with expandable output, not a durable task
history. Refreshes preserve object selection.

The navigation design follows the resource tree, selected-object content and
operations pane documented in the [Proxmox GUI guide](https://github.com/proxmox/pve-docs/blob/master/pve-gui.adoc).

## Catalog

Select a server in the sidebar. The main view shows:
- Reserved, running/starting, and stopped counts.
- Search by name, ID, profile, or public port.
- State filtering, sorting, and 25-row pagination.
- Persistent ID/name, Android API, service state, public endpoint, CPU/RAM allocation
  and default display scale.
- A selected-instance panel with storage path, disk allocation, autostart, service
  result, health, and lifecycle controls.

Running means systemd reports an active service; Health probes Android readiness.
Disk allocation is configured capacity, not measured host disk usage. Cached rows
are historical: the Linux host validates each mutation against actual state.

Server → Create instance creates a stopped AVD and stable endpoint. It suggests an unused
ID and refuses an existing ID both in the UI and on the host. Choose name, resource
preset, default resolution, and advanced image/profile/API/disk settings. Required
SDK images must already be installed; there is no unattended license acceptance.

Instance → Start boots the selected reservation. Stop shuts Android down and
retains the reservation and storage. Power cycle uses AndroidCtl's graceful
stop/start operation on the same ID. No new AVD is created.

Delete is separate: it requires DELETE followed by the exact instance ID and an
explicit keep/erase data choice. Keep retains unregistered AVD files for manual
recovery. Erase permanently deletes the AVD data. A separately saved ADB connection
can remain offline after deletion; Forget removes that connection.

## Large catalogs and runtime ports

New web-created reservations pass --runtime-ports. Example:

    sudo androidctl create 200 --runtime-ports --display-scale 50

The stable public endpoint remains remote_adb_base_port + ID (default instance 200:
15750). Only internal emulator console/ADB pairs are allocated at service preflight
under the manager lock. The allocation is recorded in the runtime reservation and
used by launch, postboot, health, shutdown and the public-port proxy. Stop releases
that runtime reservation; instance configuration, storage and public port remain.

This allows hundreds of saved catalog identities without consuming hundreds of
simultaneous emulator port pairs. Tests cover 200 saved identities and three runtime
allocations; this is not a claim of a 200-emulator hardware benchmark.

Legacy instances keep fixed internal port reservations, even when stopped. Their
pairs are excluded from the runtime pool; they are not automatically migrated.
The supported pool remains 5554–5682 (65 even console pairs). Actual concurrency
is additionally bounded by max_running_instances, available memory, CPU and GPU.
A host whose legacy reservations occupy every pair has no pool slots remaining.

Set the new concurrency limit under server diagnostics while all managed Android
instances are stopped. The field proposes a new value, not a reported current
limit; Server configuration shows the current setting. Saving a higher limit does
not bypass RAM/CPU admission checks or start any instances.

## Scoped consoles and device controls

Open console connects the selected running reservation over its public ADB endpoint
and opens its tile. Open scrcpy connects and opens native video/control on the
controller. A native desktop session and installed scrcpy are required.

Catalog entries do not create preview tiles until opened. Captures only run in the
selected object’s Console tab, for visible online tiles, while the page is visible. At most two
captures and eight total ADB subprocesses run concurrently. Browser previews are
periodic PNG screenshots (1/2/5 seconds), not video. Use scrcpy for smooth video.
Actual Android/GPU performance is separate from browser preview cadence.

Controls include volume up/down, mute, screen power, Back/Home/Apps, pointer taps
and swipes, inspection, resolution overrides, guest restart, and disconnect.
Screen power toggles display sleep/wake; it is not a VM shutdown. Use catalog Stop
to shut down Android while preserving its reservation. Enable Input ON for pointer
and navigation input. Volume/power are explicit button actions. Screen rotation
can invalidate coordinates until the next preview arrives.

Disconnect stops previews, clears stale images, closes app-owned scrcpy and retains
the connection. Network disconnect affects other clients sharing that ADB transport.
USB disconnect detaches this workbench; reconnect requires a present authorized
device. Physical phones have Forget, not virtual-instance deletion.

Connect phone/device provides network IP and port fields, USB instructions, and
wireless pairing with separate pairing/debugging ports. Pairing codes are not saved.

## Resolution and other controls

Default resolution is stored on the Linux host per instance. New reservations default
to 50%; the browser remembers the last creation choice. Choices: 25, 33, 50, 75,
100 percent. Dimensions are derived from physical size; density scales with a
minimum 72 dpi. Pixel 8 Pro at 50% is 672 × 1496 at 240 dpi. Native resets overrides.

The policy applies immediately when running and after each service boot; guest
reboots retain Android's wm overrides. Existing instances preserve old behavior
until a policy is selected. Apply now in a screen tile is a temporary override;
the next service boot restores its saved policy. If applying fails, the policy
remains saved and the operation reports the error.

Renderer changes require a stopped instance. Host GPU and software SwANGLE are
available; GPU/display setup must already work on the server. The catalog does not
install drivers or unload GPU models. Autostart, logs (last 30 minutes), instance
inspection, health, performance, doctor, GPU inventory, ports, profiles, SDK
status/images and server configuration are also available.

## CLI-to-UI map

| CLI capability | UI |
| --- | --- |
| inventory/list | Catalog, with saved state on scan failure |
| create | Selected server → Create instance |
| start/stop/restart | Selected instance: Start, Stop, Power cycle |
| enable/disable | Autostart controls |
| delete | Typed deletion dialog |
| display | Default resolution |
| renderer | Renderer selection, stopped instances |
| info/health/logs | Selected instance |
| performance/doctor/gpu list/ports/profiles | Server diagnostics |
| sdk status/images, config show | Server diagnostics |
| config set max_running_instances | Save concurrency limit |
| ADB keys, tap/swipe, connect/disconnect | Selected object → Console |
| scrcpy | Open scrcpy / Open live view |
| Interactive shells, fleet setup, SDK mutations, arbitrary config edits | CLI |

## Exports and agent use

Export connection JSON includes configured hosts, catalog/ADB endpoints and names,
and preferred creation scale. It excludes session tokens, SSH keys and operation
logs. This is a portable manifest for agents/manual restoration, not automatic import.

Export commands downloads commented Bash/Git Bash SSH, lifecycle, display, logging,
ADB and scrcpy examples. Executing the file as-is makes no changes.

Agents can start the portable web command or use the documented CLI directly.
Read .agents/skills/androidctl-workbench/SKILL.md for the existing harness workflow.
GET /api/devices and /api/hosts provide device and host inventory. POST /api/action
handles allowlisted ADB operations; POST /api/host-action handles allowlisted host
jobs. Authentication and origin checks apply to all API operations. Only one host
job runs at a time; keep the web process open until completion.

## Verification and limits

Run Python tests with PYTHONPATH=src python -m unittest discover -s tests.
DOM interaction tests use jsdom:
NODE_PATH=/path/to/node_modules node tests/workbench-ui.cjs.
Tests cover stopped identity preservation, runtime port handoff/release, 200-row
catalog pagination, selective previews, volume/power requests, deletion, creation,
exports, and failed-SSH inventory retention. Live Windows/SSH/emulator/GPU behavior
requires verification on the actual host. No browser video streaming, automatic
AVD import/recovery, cloning, snapshot restore, or automatic SSH provisioning.

## Connection troubleshooting

The tree label is a display identifier, not an SSH destination. The server form
sends separate SSH username and hostname fields; the backend constructs user@host.
For Databrick, use hostname 192.168.86.48 (or resolvable databrick), username
darkmatter2222, and SSH port 22. Review the actual target before saving.
Existing malformed profiles are not silently rewritten. Edit or remove the old
profile separately; removing it does not delete server instances.

An error containing sudo: a password is required means SSH already connected.
Instance changes require administrator-configured noninteractive sudo access for
AndroidCtl on the Linux host. The browser cannot respond to a sudo password prompt.
Operation details display the saved SSH target so errors from different profiles
can be distinguished. Polling preserves expanded operation rows and view options.

An individual running instance or device connects when its Console tab is selected.
Stopped-instance consoles explain that Android must first be started. Server console
Open buttons are built from server inventory, even before ADB discovery catches up.
