# Installation

1. Install Ubuntu 24.04 LTS x86_64 on a host with virtualization enabled in firmware. Confirm `/dev/kvm` exists and the `kvm` group owns/accesses it.
2. Clone this repository and run `sudo ./install.sh`. Review the Google license prompts. The optional `--accept-licenses` flag means you explicitly accept those licenses for automated setup.
3. Run `sudo androidctl doctor`. Resolve FAIL results before creating/starting devices. EGL/GLX warnings are diagnostic on software-only/headless hosts.
4. Run `androidctl profiles` and `androidctl sdk images` to inspect actual available inputs.

The installation uses `/opt/android-sdk`, `/usr/local/lib/androidctl`, `/usr/local/bin/androidctl`, `/etc/androidctl`, `/var/lib/androidctl`, and `/run/androidctl`. Examples in `config/` list every setting. To choose different paths or pin another command-line-tools build, create `/etc/androidctl/androidctl.conf` from the global example **before** installation. All configured paths must be absolute with no spaces or traversal. The runtime root must be a root-owned location under `/run`; the installer creates it root-owned. Do not put runtime locks on a user-writable filesystem.

`--user <SERVICE_USER>` is optional. The default creates a system account named `androidctl`, not a personal login. KVM/render/video memberships are added only when those groups exist. New services receive memberships immediately; existing interactive sessions need logout/login. The SDK is root-managed; the service account cannot replace its binaries. SDK administration uses separate root cache paths so it does not create root-owned ADB/AVD state in the service account.

The installer does not install Android Studio, a desktop, libvirt networking, Docker, GPU drivers, or kernel Binder components. The Android emulator accesses existing native KVM directly. Missing firmware virtualization cannot be safely repaired by the installer.

## Tool bootstrap and reproducibility

The global config contains a command-line-tools numeric build and official SHA-256. The URL is constructed only under Google's official `dl.google.com/android/repository/` host. A checksum mismatch stops setup. To upgrade the tools, obtain a matching build/hash pair from Google's official downloads page and update both settings, then rerun installation while devices are stopped. Existing administrator-managed `cmdline-tools/latest` directories are preserved instead of overwritten.

The manager capability-probes `android_cli` (default `/opt/android-cli/bin/android`) and prefers `android --sdk=... sdk ...` when available. If you install Google's current Android CLI separately, configure its absolute executable path. Otherwise the pinned official `sdkmanager` is used. No unverified remote install script is piped into a root shell. AVD creation/profile enumeration still use the bundled `avdmanager` compatibility interface.

The tools ZIP is pinned, but initial emulator/platform-tools and system-image package revisions are resolved from Google's stable repository. Record installed package revisions and back up the SDK for exact rebuilds; this release does not promise byte-identical SDK installations over time.

A failed final doctor returns nonzero even if files were installed successfully. Read its output and repair the host condition before retrying; existing AVD data is preserved.
