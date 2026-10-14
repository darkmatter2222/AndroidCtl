# AndroidCtl operator runbook

Used by `/androidctl deploy`, `/androidctl debug`, and `/androidctl mcp` in the current agent session. These are guided agent workflows, not unattended installers. Honor the user's scope and OpenCode's normal permissions. No operation in plugin setup deploys or starts anything.

## Deploy

1. Identify the exact target host and SSH user, fresh install versus upgrade, and desired instances. Read https://github.com/darkmatter2222/AndroidCtl and its current README, docs/installation.md and docs/fleet.md. Obtain a local checkout if needed. Inspect scripts before execution.
2. Check Ubuntu 24.04 x86_64, systemd, CPU virtualization, `/dev/kvm`, disk/RAM capacity, current AndroidCtl installation and running devices. Do not alter GPU drivers, Docker, firewall, firmware, or unrelated services. Report unsupported hosts.
3. Fresh host: use `sudo ./install.sh` from the reviewed checkout. SDK license acceptance is a user decision; never silently add `--accept-licenses`. Privilege/password/license prompts may require an interactive terminal handoff. Never store credentials in plugin config.
4. Existing host: preserve checkout changes, inspect version/configuration and back up per docs/persistence.md. Stop only managed services before the documented upgrade. Never wipe or recreate userdata to fix a boot failure.
5. Run `sudo androidctl doctor`, then `sudo androidctl fleet setup` when all managed instances are stopped. Setup creates/preserves 01–04 with saved ports; don't assume default ports for existing devices.
6. Read `androidctl adb-endpoint ID` or `androidctl fleet screen` for actual endpoints. LAN binding is opt-in while devices are stopped; use a trusted private network or tunnel. Never expose ADB publicly. Configure the viewer client with the reachable addresses; a remote 127.0.0.1 address refers to the remote host, not the desktop.
7. Start only requested instances. Verify `fleet status`, `health ID --json`, boot completion, native 1344×2992 size, density 480, proxy connectivity and restarts. Start's return is not readiness. Boot autostart is a separate user choice.
8. Install this OpenCode plugin on the desktop where windows should appear. Use `node opencode/install.mjs --host HOST --ssh USER@HOST`; preserve existing client config. Record exact results and limitations.

## Debug

- Ask for or infer the affected aliases and symptoms; read local androidctl.json for exact host/IDs. Collect `list --json`, `status ID --json`, `health ID --json`, `ports --json`, recent emulator/proxy journals, and `doctor --json` on the host. Use sudo only if needed and authorized.
- Compare service result, PID/restart counters, proxy state and boot completion. ADB connection success alone doesn't establish healthy graphics or UI automation.
- For a viewer failure inspect its log and client adb/scrcpy versions, `adb -s ENDPOINT get-state`, display session and encoder availability. Reconnect only the selected endpoint; never `adb kill-server` or global disconnect as a routine repair.
- Diagnose RenderThread crashes, KVM failures, offline ADB, port conflicts, capacity rejection and SDK/profile mismatches using docs/troubleshooting.md. Propose the smallest evidenced repair; preserve failure evidence. Coordinate any restart with the existing automation owner.
- Bounded logs may contain private data. Summarize relevant excerpts rather than publishing full logs. Verify after any approved repair; do not describe an untested change as fixed.

## MCP / automation handoff

AndroidCtl hosts VMs and does not implement screen perception, UI navigation or benchmark agents. Read https://github.com/darkmatter2222/android_automation and its actual install/configuration instructions. If access is missing, report that blocker. Configure its MCP server using the documented command and exact ADB serials; do not fabricate an executable or install an unrelated Android MCP.

Keep one input owner per device. Viewing is interactive scrcpy, so coordinate manual taps with automation. Benchmark evidence belongs to android_automation. Optional persistent goals belong to https://github.com/darkmatter2222/opencode_mastergoal; do not start forever goals without that user intent. Never claim VM health proves a benchmark passed.
