# Security model

This is a trusted administrator's management tool. ADB controls applications and guest state; its network transport must be treated as privileged. Defaults are loopback-only, and configuration rejects wildcard/public bind addresses. Explicit LAN binding still requires an appropriate external access policy. No firewall rule is installed automatically.

The emulator runs unprivileged. Code/configuration/SDK are root-owned, userdata is service-account-owned, and units apply device allowlists and filesystem restrictions. Paths and instance names are validated, subprocesses use argument arrays, and configuration values are never evaluated as shell code. A global lock protects mutations and startup admission. No runtime dependency downloads execute arbitrary scripts.

Root is trusted. A root administrator can change units, disk paths or SDK binaries; this project does not claim to contain a malicious host administrator or malicious local user with ADB access. Hardware rendering can still depend on host-driver behavior and should be validated on that host.

The official command-line-tools archive is hash-checked. Google SDK licenses require acceptance. Package binaries and images remain upstream components; keep an offline backup before updates. Repo examples contain placeholders and loopback addresses only; the private subnet constants in bind validation are policy ranges, not a real deployment.

No production credentials belong in this repository. The ignore file excludes common keys, images, AVD state, archives, local env files and logs. Review diffs and sanitize diagnostics before sharing them.
