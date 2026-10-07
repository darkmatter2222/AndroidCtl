# Architecture and lifecycle

The manager is Python standard-library code; no daemon or Python environment is required. Root owns application code, configuration, SDK packages, and unit definitions. A dedicated account owns persistent Android state. Logical IDs are canonical decimal strings (`01`, `02`, …); names and paths are separately validated.

## Service graph

`android-emulator@ID.service` requires the managed ADB server. Its root preflight validates the persistent AVD, package, KVM, selected GPU, port reservations/listeners, and host capacity under one filesystem lock. Admission writes a reservation to `/run/androidctl`. The emulator itself starts under the service identity with native acceleration forced on. A post-start helper waits for Android boot and applies optional settings. Only then may the ordered socat proxy start. The proxy is bound to and part of the emulator unit.

The postboot helper is integrated as `ExecStartPost` rather than a separate oneshot unit, so boot failure fails the primary start job. Android boot completion is distinct from process creation. Status combines systemd state, Android boot property, and proxy state.

The dedicated ADB server uses port 5038. The emulator receives matching ADB-server environment settings. The manager explicitly connects each loopback ADB endpoint and uses that endpoint as its serial. This avoids dependence on automatic discovery of console ports above historical ADB scan limits; `info` also provides the conventional `emulator-<console>` name.

## Locking and persistence

Create/delete/config/SDK operations take the host management lock. CLI start/stop enqueue systemd work while locked and release the lock before waiting. Unit preflight and stop-post also take that lock, avoiding a parent/helper lock deadlock. Boot reservations account for devices admitted but not fully running; stop-post releases reservations even after failed starts. `/run` state naturally clears on reboot. Root admins should not delete reservations while start jobs are in progress.

Port checks catch configured and live conflicts; as with any bind-then-launch design, an unrelated process can bind between validation and emulator startup. Such a race fails the start rather than selecting another port. systemd reports the error and limits restarts.

AVD creation is never forced. If creation or registration is interrupted, potentially valuable AVD files remain for explicit recovery. A retry refuses to overwrite them. Unregistered preserved data is never automatically purged.

## Isolation limits

`DevicePolicy=closed` and per-instance device allowlists prevent another physical GPU being selected. KVM and basic pseudo-devices remain available. The account's supplementary groups are detected on install; no numeric group IDs are embedded. Read-only system protection, private temporary directories, and no-new-privileges are enabled.

This is an administrator tool for trusted workloads, not a hostile multi-tenant boundary. Local users who can connect to the managed loopback ADB server can control managed guests. Instance configs are administrator-owned; guests do not receive these files. For strong user separation, use distinct hosts/VMs and an appropriately designed access layer.
