# Offline upgrades and rollback

1. Back up stopped AVDs/configuration as described in persistence.md.
2. Stop every managed instance. The upgrade refuses active or transitioning devices.
3. Fetch/review the desired repository version (`git pull --ff-only` or check out a reviewed tag/commit).
4. Run `sudo ./upgrade.sh`.
5. Run doctor, start one device, verify its app data, then start others.

The upgrade copies manager code, renders systemd templates and GPU policies, reloads systemd, and stops the managed ADB server so its next start uses the current settings. It preserves saved instance configuration and AVDs. It does not download/update SDK packages or recreate devices. The previous Python package is retained as `androidctl.previous` inside the installation directory for inspection; for rollback, check out the prior repository commit and rerun `upgrade.sh` while stopped.

SDK upgrades are separate: `sudo androidctl sdk update` requires all managed instances stopped. Current Android CLI is preferred if capability-detected, with sdkmanager fallback. A package-manager failure does not trigger a second installer automatically. Archive installed SDK revisions first; emulator/system-image compatibility must be revalidated after upgrades.

To refresh pinned command-line tools, update the build/hash configuration using Google's official download page, then run `install.sh` offline from device activity. Verify any existing `cmdline-tools/latest` directory/symlink so you know which version is active. AndroidCtl will not overwrite an administrator-managed directory automatically.

Changing service identity or storage roots is a manual offline migration. Back up, copy with ownership/permissions, update pointer paths and config, then run `upgrade.sh`. Never merely point two instances to the same writable data.
