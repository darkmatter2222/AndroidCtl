# Remote application access

There are two independent permissions. SSH authenticates your Linux login; sudo
allows that login to perform selected AndroidCtl management operations as root.
A successful inventory scan does not prove permission to start an instance.
The application never collects SSH/sudo passwords or silently trusts host keys.

## Existing Databrick installation

Your screenshot confirms SSH login already works. On Databrick, run once:

```bash
cd /home/darkmatter2222/virtual_android
git pull --ff-only
sudo python3 scripts/setup-remote-access.py --user darkmatter2222 --repair-permissions
sudo -n /usr/local/sbin/androidctl-remote check
```

This does not stop emulators, recreate instances, or require a full SDK reinstall.
It installs a root-owned gateway and a validated, per-user sudoers rule. Setup
refuses an application installation writable by non-root users. Use the normal
installer to repair ownership if needed; do not grant access to a writable checkout.

Update and restart the controller web app as well. Select Databrick → Diagnostics
→ Test management access. Then Start/Stop/Create/Delete and display/renderer changes
use the gateway. Older servers need this setup before the updated web app can mutate
instances. There is no automatic fallback to unrestricted sudo.

## Fresh installation and upgrades

```bash
sudo ./install.sh --remote-user darkmatter2222
# Or add access during an ordinary upgrade (stop emulators first):
sudo ./upgrade.sh --remote-user darkmatter2222
```

The existing --user option selects the emulator service account; --remote-user is
separate and selects an existing human/service SSH login. They are not interchangeable.
Remote access is opt-in. Subsequent upgrades refresh the installed gateway and keep
existing authorization. Uninstall removes the gateway and its managed sudo rules.

## SSH keys on a new Windows controller

Run in PowerShell, choosing a new key filename if the suggested one already exists:

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\androidctl_ed25519"
Get-Content "$env:USERPROFILE\.ssh\androidctl_ed25519.pub" | ssh darkmatter2222@192.168.86.48 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys'
```

Verify the server fingerprint through a trusted channel when first connecting.
Use a passphrase and load the key into your SSH agent for unattended application
use. Add this entry to your Windows user .ssh/config (merge with existing entries):

```sshconfig
Host 192.168.86.48 databrick
    User darkmatter2222
    IdentityFile ~/.ssh/androidctl_ed25519
    IdentitiesOnly yes
```

Test from the same account that launches the application:

```powershell
ssh -o BatchMode=yes darkmatter2222@192.168.86.48 androidctl inventory --json
ssh -o BatchMode=yes darkmatter2222@192.168.86.48 sudo -n /usr/local/sbin/androidctl-remote check
```

The web form uses display identifier databrick, hostname 192.168.86.48, username
darkmatter2222, SSH port 22. No private key or password is stored by AndroidCtl.

## Authorization scope and revocation

The authorized login can manage all AndroidCtl instances, including deleting their
Android data. Treat it as an Android fleet administrator. The helper allows only
specified lifecycle commands, bounded display/renderer settings, creation from
installed images, and concurrency configuration. It rejects shells, arbitrary ADB,
SDK installation, service internals, alternate config paths and arbitrary config
keys. Its Python interpreter is isolated and child environment is fixed.
It does not grant passwordless access to general androidctl or arbitrary commands.

The file /etc/sudoers.d/androidctl-remote-LOGIN is root-owned, mode 0440, and checked
with visudo before activation. The helper is /usr/local/sbin/androidctl-remote.
Sudo records invocations in the system authentication journal. SSH access itself is
unchanged by revoking management access:

```bash
sudo python3 scripts/setup-remote-access.py --user darkmatter2222 --remove
sudo -k
sudo -n /usr/local/sbin/androidctl-remote check  # should fail absent other sudo grants
```

If another sudo rule already grants broader privileges, remove/review that rule
separately. The provisioner never edits unrelated rules or existing authorized_keys.

The repair option normalizes only /usr/local/lib/androidctl and the installed
/usr/local/bin/androidctl launcher to root ownership and non-group-writable modes.
It refuses symlinks and special files, and never changes AVD data, configuration,
the SDK, or the source checkout. The installer now normalizes copied code modes
instead of preserving group-write permissions from the source checkout.
