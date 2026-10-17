#!/usr/bin/env python3
"""Provision/revoke a named login's restricted AndroidCtl sudo gateway."""
import argparse
import os
from pathlib import Path
import pwd
import re
import subprocess
import tempfile
import sys

from install_permissions import secure_tree

REPO = Path(__file__).resolve().parents[1]
GATEWAY = Path('/usr/local/sbin/androidctl-remote')


def trusted(path):
    path = Path(path)
    for entry in [path, *path.parents]:
        st = entry.lstat()
        if entry.is_symlink() or st.st_uid != 0 or st.st_mode & 0o022:
            raise ValueError(f'Root-owned, non-writable installation required: {entry}')


def provision(user, remove=False, repair=False):
    if os.geteuid() != 0:
        raise ValueError('Run with sudo once to authorize this login')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*', user):
        raise ValueError('Invalid login name')
    account = pwd.getpwnam(user)
    if account.pw_uid == 0:
        raise ValueError('Choose a non-root SSH login')
    policy = Path('/etc/sudoers.d') / ('androidctl-remote-' + user)
    trusted(policy.parent)
    if remove:
        policy.unlink(missing_ok=True)
        print('Revoked AndroidCtl remote access for ' + user)
        return
    for path in (Path('/usr/local/bin/androidctl'), Path('/usr/local/lib/androidctl')):
        if repair:
            trusted(path.parent)
            secure_tree(path)
        trusted(path)
        if path.is_dir():
            for child in path.rglob('*'):
                trusted(child)
    GATEWAY.parent.mkdir(parents=True, exist_ok=True)
    trusted(GATEWAY.parent)
    content = (REPO / 'libexec/androidctl-remote').read_bytes()
    fd, temp = tempfile.mkstemp(prefix='.androidctl-', dir=GATEWAY.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(content)
        os.chmod(temp, 0o755)
        os.replace(temp, GATEWAY)
    finally:
        Path(temp).unlink(missing_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.androidctl-', dir=policy.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(f'{user} ALL=(root) NOPASSWD: {GATEWAY}\n')
        os.chmod(temp, 0o440)
        subprocess.run(['/usr/sbin/visudo', '-cf', temp], check=True)
        os.replace(temp, policy)
    finally:
        Path(temp).unlink(missing_ok=True)
    subprocess.run(['/usr/sbin/runuser', '-u', user, '--', 'sudo', '-n', str(GATEWAY), 'check'], check=True)
    print('Remote access ready for ' + user + '. SSH keys remain managed by your login.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', required=True)
    parser.add_argument('--remove', action='store_true')
    parser.add_argument('--repair-permissions', action='store_true',
                        help='Normalize installed application ownership/modes; preserve Android data')
    args = parser.parse_args()
    if args.remove and args.repair_permissions:
        parser.error('--remove and --repair-permissions cannot be combined')
    try:
        provision(args.user, args.remove, args.repair_permissions)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print('ERROR: ' + str(exc), file=sys.stderr)
        if not args.remove:
            print('For an existing regular-file installation, retry with --repair-permissions.', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
