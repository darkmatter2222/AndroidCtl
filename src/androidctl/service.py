"""Internal systemd entry points. No shell interpolation of configuration."""

import json
import os
import signal
import socket
import time
from pathlib import Path

from . import adb, avd, gpu, host, ports, systemd
from .config import instances
from .errors import Error
from .sdk import SDK, environment
from .util import atomic_write, lock, require_root


def reservation(cfg, ident):
    return Path(cfg.runtime_root) / f"reserved-{ident}.json"


def preflight(cfg, obj):
    require_root()
    with lock(cfg):
        host.check_kvm()
        data, pointer = avd.paths(cfg, obj)
        if not (data / "config.ini").is_file() or not pointer.is_file():
            raise Error("Persistent AVD or pointer is missing.", 5)
        if not SDK(cfg).installed(obj.package):
            raise Error("Configured system image is no longer installed.", 8)
        gpu.selection(obj)
        all_instances = instances(cfg)
        ports.conflicts(obj, all_instances, cfg.adb_server_port)
        ports.available((obj.console_port, obj.local_adb_port, obj.remote_adb_port))
        marker = Path(cfg.runtime_root) / f"force-{obj.id}"
        force = marker.exists()
        marker.unlink(missing_ok=True)
        reserved = {
            p.name[9:-5]: json.loads(p.read_text()) for p in Path(cfg.runtime_root).glob("reserved-*.json")
        }
        active = [
            i
            for i in all_instances
            if i.id != obj.id
            and (i.id in reserved or systemd.properties(i.id).get("ActiveState") == "active")
        ]
        # Reserve memory for all admitted but not yet booted emulators. Running
        # RSS is already reflected in MemAvailable; avoid counting it twice.
        pending_mb = sum(i.ram_mb for i in active if systemd.properties(i.id).get("ActiveState") != "active")
        if not force and (
            len(active) >= cfg.max_running_instances
            or host.available_ram() - pending_mb - obj.ram_mb < cfg.minimum_free_ram_mb
            or obj.cpu_cores > (os.cpu_count() or 1)
        ):
            raise Error(
                f"Resource limit: {len(active)} admitted/running, maximum {cfg.max_running_instances}; RAM or CPU reserve insufficient. CLI --force overrides only resources.",
                7,
            )
        address = host.bind_address(cfg)
        with socket.socket() as sock:
            try:
                sock.bind((address, obj.remote_adb_port))
            except OSError as exc:
                raise Error(
                    f"Cannot bind configured endpoint {address}:{obj.remote_adb_port}: {exc}", 6
                ) from exc
        atomic_write(Path(cfg.runtime_root) / f"endpoint-{obj.id}", address + "\n")
        atomic_write(reservation(cfg, obj.id), json.dumps({"ram_mb": obj.ram_mb, "id": obj.id}))
        print(f"Preflight OK; endpoint {address}:{obj.remote_adb_port}", flush=True)


def release(cfg, obj):
    require_root()
    with lock(cfg):
        reservation(cfg, obj.id).unlink(missing_ok=True)
        (Path(cfg.runtime_root) / f"force-{obj.id}").unlink(missing_ok=True)


def launch(cfg, obj):
    if os.geteuid() == 0:
        raise Error("Emulator must run as the configured non-root service user.", 5)
    env = environment(cfg)
    env.update(gpu.environment(obj))
    args = [
        SDK(cfg).tool("emulator"),
        "-avd",
        obj.name,
        "-port",
        str(obj.console_port),
        "-memory",
        str(obj.ram_mb),
        "-cores",
        str(obj.cpu_cores),
        "-gpu",
        obj.gpu_mode,
        "-accel",
        "on",
        "-no-window",
        "-no-audio",
        "-no-boot-anim",
        "-no-snapshot",
        "-camera-back",
        "none",
        "-camera-front",
        "none",
    ]
    # Block physical fallback via cgroup DevicePolicy; no writable-system,
    # wipe-data, read-only multiinstance, or automatic snapshot flags.
    os.execve(args[0], args, env)


def postboot(cfg, obj):
    deadline = time.monotonic() + cfg.boot_timeout
    while time.monotonic() < deadline:
        try:
            adb.connect(cfg, obj)
            if adb.booted(cfg, obj):
                break
        except Error:
            pass
        time.sleep(2)
    else:
        raise Error("Android boot timeout; check renderer and emulator journal.", 9)
    if cfg.postboot:
        commands = [
            ["shell", "settings", "put", "global", "development_settings_enabled", "1"],
            ["shell", "svc", "power", "stayon", "true"],
            ["shell", "settings", "put", "system", "screen_off_timeout", "2147483647"],
        ]
        if cfg.disable_animations:
            commands += [
                ["shell", "settings", "put", "global", key, "0"]
                for key in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale")
            ]
        for args in commands:
            adb.command(cfg, obj, args)
    print("Android boot completed; postboot settings applied.", flush=True)


def graceful_stop(cfg, obj):
    pid = int(os.environ.get("MAINPID", "0"))
    if pid <= 1:
        return

    def alive():
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False

    try:
        adb.command(cfg, obj, ["shell", "sync"], check=False, timeout=10)
        adb.command(cfg, obj, ["emu", "kill"], check=False, timeout=10)
    except Error as exc:
        print(f"Graceful ADB request unavailable: {exc}", flush=True)
    deadline = time.monotonic() + cfg.stop_timeout
    while alive() and time.monotonic() < deadline:
        time.sleep(1)
    if alive():
        print(
            "WARNING: graceful stop timed out; sending SIGTERM. systemd will use SIGKILL only after its final timeout.",
            flush=True,
        )
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + 15
        while alive() and time.monotonic() < deadline:
            time.sleep(1)
        if alive():
            print(
                "WARNING: process did not exit after SIGTERM; handing final escalation to systemd.",
                flush=True,
            )


def proxy(cfg, obj):
    address = (Path(cfg.runtime_root) / f"endpoint-{obj.id}").read_text().strip()
    from dataclasses import replace

    replace(cfg, bind_address=address).validate()
    args = [
        "/usr/bin/socat",
        f"TCP4-LISTEN:{obj.remote_adb_port},bind={address},reuseaddr,fork",
        f"TCP4:127.0.0.1:{obj.local_adb_port}",
    ]
    os.execv(args[0], args)


def adb_server(cfg):
    args = [SDK(cfg).tool("adb"), "-L", f"tcp:127.0.0.1:{cfg.adb_server_port}", "server", "nodaemon"]
    os.execve(args[0], args, environment(cfg))
