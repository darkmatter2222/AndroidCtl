from pathlib import Path

from . import gpu
from .util import atomic_write, run


def unit(ident, kind="emulator"):
    return f"android-{kind}@{ident}.service"


def action(verb, ident, kind="emulator", wait=True):
    args = ["systemctl", verb]
    if not wait:
        args.append("--no-block")
    return run(args + [unit(ident, kind)], timeout=None)


def properties(ident):
    p = run(
        [
            "systemctl",
            "show",
            unit(ident),
            "--property=ActiveState,SubState,MainPID,ActiveEnterTimestamp,Result",
        ],
        check=False,
    )
    if p.returncode:
        return {"ActiveState": "unknown", "MainPID": "0"}
    return dict(line.split("=", 1) for line in p.stdout.splitlines() if "=" in line)


def active(ident, kind="emulator"):
    return run(["systemctl", "is-active", "--quiet", unit(ident, kind)], check=False).returncode == 0


def gpu_policy(instance):
    dev = gpu.selection(instance)
    nodes = dev["nodes"] if dev else []
    path = Path("/etc/systemd/system") / (unit(instance.id) + ".d") / "devices.conf"
    atomic_write(
        path,
        "[Service]\nDevicePolicy=closed\nDeviceAllow=\nDeviceAllow=/dev/kvm rw\n"
        + "".join(f"DeviceAllow={n} rw\n" for n in nodes),
    )
    run(["systemctl", "daemon-reload"])


def remove_policy(ident):
    path = Path("/etc/systemd/system") / (unit(ident) + ".d") / "devices.conf"
    path.unlink(missing_ok=True)
    if path.parent.exists() and not list(path.parent.iterdir()):
        path.parent.rmdir()
    run(["systemctl", "daemon-reload"])
