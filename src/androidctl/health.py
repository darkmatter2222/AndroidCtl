from dataclasses import asdict
from pathlib import Path
import socket

from . import adb, systemd
from .errors import Error
from .config import runtime_instance
from .host import bind_address


def classify(active, boot, proxy):
    if active == "inactive":
        return "stopped", "unknown"
    if active == "failed":
        return "failed", "unhealthy"
    if active == "deactivating":
        return "stopping", "unknown"
    if active == "activating":
        return "starting", "degraded"
    if active == "active":
        return ("running", "healthy" if proxy else "degraded") if boot else ("booting", "degraded")
    return "unknown", "unknown"


def status(cfg, instance):
    instance = runtime_instance(cfg, instance)
    props = systemd.properties(instance.id)
    boot = False
    if props.get("ActiveState") in ("active", "activating"):
        try:
            boot = adb.booted(cfg, instance)
        except Error:
            pass
    proxy = systemd.active(instance.id, "adb-proxy") if boot else False
    try:
        saved = Path(cfg.runtime_root) / f"endpoint-{instance.id}"
        address = (
            saved.read_text().strip()
            if props.get("ActiveState") in ("active", "activating") and saved.exists()
            else bind_address(cfg)
        )
        endpoint = f"{address}:{instance.remote_adb_port}"
        if proxy:
            with socket.create_connection((address, instance.remote_adb_port), timeout=2):
                pass
    except (Error, OSError):
        endpoint = "unresolved"
        proxy = False
    process_alive = int(props.get("MainPID", "0")) > 0
    state, health = classify(props.get("ActiveState"), boot and process_alive, proxy)
    result = asdict(instance)
    result.update(
        state=state,
        health=health,
        endpoint=endpoint,
        serial=instance.serial,
        emulator_serial=f"emulator-{instance.console_port}",
        pid=int(props.get("MainPID", "0")),
        boot_completed=boot,
        active_since=props.get("ActiveEnterTimestamp", ""),
        service_result=props.get("Result", ""),
        avd=f"{cfg.avd_root}/{instance.name}.avd",
    )
    if boot:
        try:
            result["android_release"] = adb.command(
                cfg, instance, ["shell", "getprop", "ro.build.version.release"]
            ).stdout.strip()
        except Error:
            result["android_release"] = "unknown"
    return result


def inventory(cfg, instance):
    """Registered storage and service state without waiting on guest ADB."""
    instance = runtime_instance(cfg, instance)
    props = systemd.properties(instance.id)
    active = props.get("ActiveState", "unknown")
    states = {
        "active": "running",
        "inactive": "stopped",
        "failed": "failed",
        "activating": "starting",
        "deactivating": "stopping",
    }
    result = asdict(instance)
    result.update(
        state=states.get(active, "unknown"),
        health="not probed",
        service_result=props.get("Result", ""),
        pid=int(props.get("MainPID", "0")),
        avd=f"{cfg.avd_root}/{instance.name}.avd",
        active_since=props.get("ActiveEnterTimestamp", ""),
    )
    if instance.runtime_ports and not (Path(cfg.runtime_root) / f"reserved-{instance.id}.json").exists():
        result["console_port"] = None
        result["local_adb_port"] = None
    return result
