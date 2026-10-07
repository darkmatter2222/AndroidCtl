# Persistent data and offline backup

Normal launches use `-no-snapshot`, not `-wipe-data`. AVD userdata is private per name. Start/stop/reboot/manager upgrades do not recreate AVDs. Image upgrades may still have Android compatibility implications; keep backups.

For a consistent manual backup:

1. `sudo androidctl stop ID` and verify stopped state.
2. Copy `/etc/androidctl/androidctl.conf`, `/etc/androidctl/instances/ID.conf`, the matching `<NAME>.ini`, and the entire `<NAME>.avd/` from the configured AVD root. Use `sudo cp -a --sparse=always` or a sparse-aware archive tool to a local protected backup destination.
3. Preserve ownership and permissions. AVD files include personal app data and potentially credentials; do not publish them or commit them.
4. Store the relevant SDK image revision too for reproducibility. Record `androidctl sdk status` and the package's `source.properties`.
5. Generate/verify a checksum of the completed archive using `sha256sum`. Resume the source only after backup copying finishes.

Restore only while all relevant devices are stopped. Verify the archive checksum, restore files to their original paths, and restore service-account ownership. Inspect the `.ini` pointer's absolute path. Run `sudo ./upgrade.sh` from the repository to reinstall/regenerate unit definitions and device policies, then verify `doctor`, `ports`, and `status` before starting. The installer never overwrites preserved AVD data.

Restoring under a different logical ID/name or cloning requires carefully rewriting internal references and ensuring no writable disks are shared. It is **not supported by an automated v1 command**. Create independent AVDs when separate identity is required; Android-generated identifiers are not derived from the management ID.

`delete ID --keep-data` deliberately leaves an unregistered AVD/pointer. Re-creating the same name refuses to overwrite it. Recover by restoring its saved config; erase orphan data only after explicit manual inspection. Default uninstall preserves all configuration and AVDs. Purge only deletes registered AVDs and configurations, preserving unrelated and unregistered data.
