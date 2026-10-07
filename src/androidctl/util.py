import contextlib
import fcntl
import os
import subprocess
import tempfile
from pathlib import Path

from .errors import Error


def run(args, *, check=True, timeout=60, capture=True, **kwargs):
    try:
        p = subprocess.run(
            [str(a) for a in args], text=True, capture_output=capture, check=False, timeout=timeout, **kwargs
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Error(f"Cannot run {args[0]}: {exc}", 5) from exc
    if check and p.returncode:
        raise Error(f"{args[0]} failed ({p.returncode}): {(p.stderr or p.stdout or '').strip()}", 5)
    return p


def atomic_write(path, text, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".androidctl-")
    try:
        with os.fdopen(fd, "w") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextlib.contextmanager
def lock(cfg):
    root = Path(cfg.runtime_root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "manager.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def require_root():
    if os.geteuid() != 0:
        raise Error("This operation requires sudo/root.", 5)
