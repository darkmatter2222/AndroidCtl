# OpenCode AndroidCtl plugin v0.1.1

- Fix `/androidctl A` and other direct commands injecting output into the AI chat. Direct commands now run in the terminal client, show transient toasts/dialogs, and never call session/model APIs. The old server command and synthetic message were removed.
- Keep help, status, logs, errors and partial failures outside chat too. Prevent concurrent repeated submission while a command is still running.
- Run scrcpy on the terminal client's desktop even with a remote OpenCode server.
- Default installation now registers a managed Git package tracking main. Native `/plugins` check/update can update it without re-entering a URL. The installer migrates the original local copy into a backup and preserves androidctl.json.
- Add terminal plugin exports and migration/no-chat regression tests. Explicit deploy/debug/MCP agent workflows still intentionally use the current chat agent.

## Updating

Managed main installs: `/plugins` → check for updates → select AndroidCtl's Server package entry → update. Alternatively run `opencode plugin check` and `opencode plugin update`.

Original copied/local installs: update your AndroidCtl checkout to main, run `node opencode/install.mjs` once, then restart OpenCode. This migrates the local copy into a managed package without replacing your device settings. Manually configured local paths must also be removed from OpenCode config. Future updates use `/plugins`.

The release ZIP is an optional source bundle. Extracting a ZIP is not a managed installation; use its installer to register the package.

Validation: 13 automated plugin tests, including zero session API access for direct commands. Type-checked against @opencode/plugin 2.0.29. Actual GUI/SSH/KVM behavior requires the user's desktop/devices.
