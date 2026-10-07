# Troubleshooting

| Symptom | Checks and action |
|---|---|
| Missing `/dev/kvm` | Enable firmware virtualization; inspect KVM modules. On a VM, confirm supported nested KVM. No software CPU emulation fallback is used. |
| Acceleration denied | Run `sudo androidctl doctor`; check the configured service account's kvm group membership and device permissions. |
| Profile unavailable | Use `androidctl profiles`; upgrade command-line tools or explicitly choose a listed profile. |
| Image unavailable | Inspect `androidctl sdk images`; image variant/architecture availability differs by API. |
| SDK license rejected | Run `sudo androidctl sdk licenses`, review/accept, retry installation. |
| Port occupied | Follow the error's `sudo ss -ltnp 'sport = :PORT'` command. Change the conflicting workload or explicitly choose unused permanent ports. |
| Starting/booting never healthy | Inspect `sudo androidctl logs ID --follow`; Android must finish boot and the proxy must start. |
| Renderer crash | Inspect selected GPU, service device policy and graphics libraries; try a supported software renderer while stopped. |
| Start limit hit | Repair the cause, then `sudo systemctl reset-failed android-emulator@ID.service` and start again. |
| Resource limit | Check `MemAvailable`, configured RAM/reserve and active devices. Reduce load or deliberately use `start ID --force`. |
| Remote client refused | Default bind is loopback. Check endpoint, proxy journal, existing firewall policy and LAN address. Use SSH tunneling if appropriate. |
| ADB offline | Check managed `android-adb.service` journal, emulator boot logs and `androidctl adb ID get-state`. |
| scrcpy audio fails | Add `--no-audio`; inspect client-supported encoders/options. |
| Creation interrupted | Inspect retained AVD data and pointer. Retry refuses to overwrite them; recover config or explicitly remove only confirmed disposable orphan data. |
| Forced shutdown warning | Inspect journal and storage health before restarting. SIGKILL is the last systemd escalation, not normal operation. |
| CLI works but boot autostart GPU fails | Regenerate unit policies with offline `upgrade.sh` after manual GPU config edits. |

Useful commands: `sudo androidctl doctor --json`, `androidctl status ID --json`, `sudo journalctl -u android-adb.service`, `sudo systemctl status android-emulator@ID.service`, and `sudo ss -ltnp`.

Do not post unredacted diagnostics publicly: local hostnames, interface addresses, serials, paths and application data may be present. Never upload `.android/adbkey`, full AVDs or private configuration as an issue attachment.
