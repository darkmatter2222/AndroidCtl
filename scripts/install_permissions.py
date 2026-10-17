"""Normalize only installed application code, never instance data or configuration."""
import os
import stat
from pathlib import Path


def secure_tree(root):
    root = Path(root)
    entries = [root, *root.rglob('*')] if root.is_dir() and not root.is_symlink() else [root]
    # Validate everything before changing any ownership or permissions.
    for entry in entries:
        mode = entry.lstat().st_mode
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise ValueError(f'Refusing symlink or special file in application installation: {entry}')
    for entry in entries:
        mode = entry.lstat().st_mode
        os.chown(entry, 0, 0, follow_symlinks=False)
        os.chmod(entry, 0o755 if stat.S_ISDIR(mode) or mode & 0o111 else 0o644)
