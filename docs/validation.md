# Validation and release limitations

## Hardware-independent checks

Run `PYTHONPATH=src python3 -m unittest discover -s tests -v`, Ruff lint/format, ShellCheck and `python3 scripts/validate_units.py`. CI runs these without KVM. The unit validator replaces executable paths only for systemd syntax/dependency validation; it does not claim the target host has installed the SDK.

Tests exercise numeric port boundaries and actual socket collision detection, config round trips/rejections, duplicate identities, destructive-action refusal, kept data, symlink rejection, lifecycle state mapping, safe launch flags, stop ordering, SDK command compatibility/profile parsing, GPU opt-in and autostart resource admission.

## Required Ubuntu/KVM acceptance checks

Use disposable test devices before trusting important data:

1. Fresh Ubuntu 24.04 installation: install, doctor, profile/image discovery.
2. Create instance 01 on API 35 and 02 on API 34 with an actual available profile. Verify distinct AVD directories and saved ports.
3. Start 01; verify Android release, boot completion, proxy health, PID and endpoint. Inspect `ss -ltnp`: console/local ADB and managed ADB server must be loopback-only.
4. Connect with Windows ADB/scrcpy using SSH forwarding or explicit trusted LAN binding.
5. Install a disposable app or write a marker. Run `sudo scripts/test-host.sh --instance 01` starting with a stopped instance. This tests marker persistence through restart and leaves it stopped.
6. Enable a disposable device, reboot explicitly, verify its data/ports, then disable it. Reboot is a host-admin action, never triggered by these scripts.
7. Start two devices concurrently and confirm the configured limit/reservations prevent a third. Repeat via direct systemd jobs and boot-time autostart.
8. Test an occupied port; verify failure with no alternate assignment. Test a broken renderer; confirm bounded restarts and useful journal errors.
9. Stop and wait; verify it does not restart. Inspect that normal stop avoids force escalation.
10. Test upgrade/default uninstall and reinstall: configurations and userdata must remain. Test `delete --keep-data` separately. Test destructive purge only against disposable data after reading its printed scope.
11. Test a selected Mesa device with another GPU busy on unrelated work. Confirm allowlists and actual GPU activity; no driver or unrelated workload configuration may change.

## Scope

Real KVM/emulator/GPU/LAN/reboot tests were not available in the build workspace. Completion of automated checks is not a claim of hardware validation. Current and legacy SDK command generation are mocked; verify the installed Google tool versions on the host. The pinned archive/hash came from Google's official download page but the multi-hundred-megabyte SDK was not installed into the build container.

v1 excludes automatic clone/snapshot/backup/restore, live disk resize, live migration, proprietary NVIDIA selection, and non-Ubuntu/non-x86_64 hosts. The SDK package revisions beyond the bootstrap ZIP are not fully pinned. Advanced custom paths should be validated locally, especially permissions and systemd filesystem protection. Stop timeouts can require force; inspect any warning before treating a shutdown as clean.
