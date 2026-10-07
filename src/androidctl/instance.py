"""Administrative mutations; the unit's preflight also covers boot and restarts."""

import shutil
import time
from dataclasses import replace
from pathlib import Path

from . import avd, gpu, ports, systemd
from .config import Instance, instances, save
from .errors import Error
from .health import status
from .sdk import SDK
from .util import atomic_write, lock


def create(cfg, args):
    with lock(cfg):
        ident = ports.normalize_id(args.id)
        existing = instances(cfg)
        if any(i.id == ident for i in existing):
            raise Error(f"Instance {ident} already exists.", 4)
        profile = args.profile or cfg.default_profile
        api = cfg.default_api if args.api is None else args.api
        normalized = "".join(w.capitalize() if not w.isdigit() else w for w in profile.split("_"))
        console, local, remote = ports.allocate(
            ident, cfg.console_base_port, cfg.remote_adb_base_port, args.console_port, args.remote_adb_port
        )
        obj = Instance(
            id=ident,
            name=args.name or f"{normalized}_API{api}_{ident}",
            api=api,
            profile=profile,
            image=args.image or cfg.default_image,
            architecture=args.architecture,
            console_port=console,
            local_adb_port=local,
            remote_adb_port=remote,
            ram_mb=cfg.default_ram_mb if args.ram is None else args.ram,
            cpu_cores=cfg.default_cpu_cores if args.cpus is None else args.cpus,
            disk_size=args.disk or cfg.default_disk_size,
            gpu_mode=args.gpu or cfg.default_gpu_mode,
            gpu_pci=args.gpu_pci or "",
            dri_prime=cfg.dri_prime,
        ).validate()
        if any(i.name == obj.name for i in existing):
            raise Error("AVD name already registered.", 4)
        ports.conflicts(obj, existing, cfg.adb_server_port)
        ports.available((console, local, remote))
        gpu.selection(obj)
        sdk = SDK(cfg)
        profiles = sdk.profiles()
        if not any(p["id"] == profile for p in profiles):
            raise Error(
                f"Profile {profile} unavailable. Run androidctl profiles; no substitute was selected.", 8
            )
        if not sdk.installed(obj.package):
            if obj.package not in sdk.images():
                raise Error(f"Image {obj.package} unavailable. Run androidctl sdk images.", 8)
            if not args.install_image:
                import sys

                if not sys.stdin.isatty() or input(f"Install {obj.package}? [Y/n] ").strip().lower() not in (
                    "",
                    "y",
                    "yes",
                ):
                    raise Error("Image installation declined; use --install-image for automation.", 8)
            sdk.install([obj.package])
        if shutil.disk_usage(cfg.avd_root).free < obj.ram_mb * 1024 * 1024:
            raise Error("Insufficient filesystem space even for initial AVD allocation.", 7)
        # Never overwrite an unregistered AVD left by an interrupted creation.
        avd.create(cfg, obj)
        try:
            systemd.gpu_policy(obj)
            save(Path(cfg.instance_root) / f"{ident}.conf", obj, "instance")
        except (Error, OSError) as exc:
            # Preserve data for explicit recovery after an interrupted operation.
            raise Error(
                f"AVD {obj.name} created but registration failed; retained at {cfg.avd_root}. Inspect before retrying."
            ) from exc
    return obj


def start(cfg, obj, force=False):
    with lock(cfg):
        if systemd.properties(obj.id).get("ActiveState") in ("active", "activating", "deactivating"):
            raise Error("Instance already running or transitioning; inspect status first.", 4)
        systemd.gpu_policy(obj)
        marker = Path(cfg.runtime_root) / f"force-{obj.id}"
        marker.unlink(missing_ok=True)
        if force:
            atomic_write(marker, "resource override for next preflight\n", 0o600)
        try:
            systemd.action("start", obj.id, wait=False)
        except (Error, OSError):
            marker.unlink(missing_ok=True)
            raise
    deadline = time.monotonic() + cfg.boot_timeout + 30
    while time.monotonic() < deadline:
        view = status(cfg, obj)
        if view["health"] == "healthy":
            return view
        if view["state"] == "failed":
            raise Error(f"Startup failed. Inspect androidctl logs {obj.id}.", 9)
        time.sleep(2)
    # A start timeout is a failed start, not an invisible background attempt.
    stop(cfg, obj)
    raise Error("Startup timed out; device stopped. Inspect logs and renderer/boot settings.", 9)


def stop(cfg, obj):
    # The unit's ExecStop syncs and requests emulator exit. systemd marks this
    # an intentional stop, so Restart=on-failure cannot restart it.
    with lock(cfg):
        systemd.action("stop", obj.id, wait=False)
    deadline = time.monotonic() + cfg.stop_timeout + 90
    while time.monotonic() < deadline:
        props = systemd.properties(obj.id)
        if props.get("ActiveState") in ("inactive", "failed"):
            if props.get("Result") in ("timeout", "signal", "core-dump"):
                print("WARNING: forced termination or prior crash recorded; inspect journald.")
            return
        time.sleep(1)
    raise Error("systemd shutdown did not finish; inspect status and journal before retrying.", 9)


def enable(cfg, obj, value):
    with lock(cfg):
        systemd.action("enable" if value else "disable", obj.id)
        save(Path(cfg.instance_root) / f"{obj.id}.conf", replace(obj, autostart=value), "instance")


def delete(cfg, obj, yes=False, keep_data=False):
    import sys

    if not yes:
        if not sys.stdin.isatty():
            raise Error("Deletion requires interactive confirmation or --yes.", 11)
        if input(
            f"Delete instance {obj.id} ({'preserve' if keep_data else 'permanently erase'} userdata at {cfg.avd_root}/{obj.name}.avd)? [y/N] "
        ).lower() not in ("y", "yes"):
            raise Error("Deletion cancelled.", 11)
    stop(cfg, obj)
    with lock(cfg):
        if systemd.properties(obj.id).get("ActiveState") not in ("inactive", "failed"):
            raise Error("Instance restarted concurrently; refusing deletion.", 11)
        systemd.action("disable", obj.id)
        systemd.remove_policy(obj.id)
        if not keep_data:
            avd.remove(cfg, obj)
        (Path(cfg.instance_root) / f"{obj.id}.conf").unlink()
