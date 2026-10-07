# Changelog

## Unreleased

- Keep interactive ADB/SDK clients in the executing account’s Android home while connecting to the shared managed ADB server. Fix non-root permission failures and false degraded status without relaxing service-home permissions.

- Fix ADB server crash on releases that reject numeric hosts in listener socket specifications. Use loopback-default `tcp:PORT` for both the managed server and client environment; never enable all-interface listening.

## 0.1.0 — 2026-10-07

- Initial native Ubuntu/KVM AndroidCtl implementation.
- Persistent per-instance AVDs, multiple API images, permanent ports, validated profiles.
- systemd lifecycle, boot detection, bounded crash restarts and controlled shutdown.
- Loopback-first ADB proxy, explicit Mesa GPU selection and software rendering.
- Resource admission across CLI, systemd and autostart; serialized SDK/config mutations.
- Installer, offline upgrade, data-preserving uninstall, tests, CI and operational docs.
- Real-host KVM/GPU acceptance remains required; see validation documentation.
