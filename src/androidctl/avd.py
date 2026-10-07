import os
import pwd
import shutil
from pathlib import Path

from .errors import Error
from .sdk import SDK, environment
from .util import atomic_write, run


def paths(cfg, instance):
    root = Path(cfg.avd_root).resolve()
    avd = root / f"{instance.name}.avd"
    pointer = root / f"{instance.name}.ini"
    if avd.is_symlink() or pointer.is_symlink():
        raise Error("Refusing symlinked AVD/pointer; writable disks must be isolated.")
    return avd, pointer


def create(cfg, instance):
    avd, pointer = paths(cfg, instance)
    if avd.exists() or pointer.exists():
        raise Error("AVD data already exists; refusing to overwrite preserved userdata.", 4)
    sdk = SDK(cfg)
    account = pwd.getpwnam(cfg.service_user)
    # SDK is root-managed; the AVD and its pointer are service-user-owned.
    run(
        [
            "runuser",
            "-u",
            cfg.service_user,
            "--",
            sdk.tool("avdmanager"),
            "create",
            "avd",
            "--name",
            instance.name,
            "--package",
            instance.package,
            "--device",
            instance.profile,
            "--path",
            avd,
        ],
        env=environment(cfg),
        input="no\n",
        timeout=120,
    )
    values = {}
    for line in (avd / "config.ini").read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    values.update(
        {
            "hw.ramSize": str(instance.ram_mb),
            "hw.cpu.ncore": str(instance.cpu_cores),
            "disk.dataPartition.size": instance.disk_size,
            "hw.gpu.enabled": "yes",
            "hw.gpu.mode": instance.gpu_mode,
            "hw.camera.back": "none",
            "hw.camera.front": "none",
        }
    )
    atomic_write(avd / "config.ini", "".join(f"{k}={v}\n" for k, v in values.items()), 0o600)
    os.chown(avd / "config.ini", account.pw_uid, account.pw_gid)


def remove(cfg, instance):
    avd, pointer = paths(cfg, instance)
    if avd.exists():
        shutil.rmtree(avd)
    pointer.unlink(missing_ok=True)
