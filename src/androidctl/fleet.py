"""Four persistent systemd devices; SSH clients only submit jobs or observe."""

import json
import logging
import os
import pwd
import shutil
import time
from dataclasses import replace
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import avd, health, systemd
from .config import get_instance, instances, save
from .errors import Error
from .ports import normalize_id
from .util import atomic_write, lock, require_root, run

IDS = ("01", "02", "03", "04")
CONFIG = "/etc/androidctl/androidctl.conf"


def selected(ids):
    result = list(dict.fromkeys(normalize_id(i) for i in ids)) if ids else list(IDS)
    if any(i not in IDS for i in result):
        raise Error("Fleet IDs must be 01, 02, 03 or 04.")
    return result


def configure_display(cfg, obj):
    data, _ = avd.paths(cfg, obj)
    path = data / "config.ini"
    values = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    values.update(
        {
            "hw.lcd.width": "1344",
            "hw.lcd.height": "2992",
            "hw.lcd.density": "480",
            "skin.name": "1344x2992",
            "skin.path": "1344x2992",
            "showDeviceFrame": "no",
            "hw.gpu.enabled": "yes",
            "hw.gpu.mode": "swangle",
        }
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    shutil.copy2(path, path.with_name("config.ini.backup-" + stamp))
    account = pwd.getpwnam(cfg.service_user)
    atomic_write(path, "".join(f"{k}={v}\n" for k, v in values.items()), 0o600)
    os.chown(path, account.pw_uid, account.pw_gid)


def setup(cfg, api):
    require_root()
    # Creation takes its own manager lock; recheck under lock before final edits.
    for obj in instances(cfg):
        if systemd.properties(obj.id).get("ActiveState") not in ("inactive", "failed"):
            raise Error("Stop all managed devices before fleet setup.")
    for ident in IDS:
        existing = {o.id: o for o in instances(cfg)}
        if ident in existing:
            if existing[ident].profile != "pixel_8_pro" or existing[ident].api != api:
                raise Error(f"{ident} has a different profile/API; preserved, not replaced.")
        else:
            run(
                [
                    "/usr/local/bin/androidctl",
                    "create",
                    ident,
                    "--api",
                    str(api),
                    "--profile",
                    "pixel_8_pro",
                    "--gpu",
                    "swangle",
                    "--install-image",
                ],
                timeout=None,
                capture=False,
            )
    with lock(cfg):
        if any(
            systemd.properties(o.id).get("ActiveState") not in ("inactive", "failed") for o in instances(cfg)
        ):
            raise Error("A device started during setup; stop it and retry.")
        for ident in IDS:
            obj = get_instance(cfg, ident)
            configure_display(cfg, obj)
            path = Path(cfg.instance_root) / f"{ident}.conf"
            shutil.copy2(
                path,
                path.with_suffix(
                    ".conf.pre-fleet-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                ),
            )
            obj = replace(obj, gpu_mode="swangle", native_pixel_display=True, disable_guest_vulkan=True)
            save(path, obj, "instance")
            systemd.gpu_policy(obj)
        shutil.copy2(CONFIG, CONFIG + ".pre-fleet-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        save(CONFIG, replace(cfg, max_running_instances=max(4, cfg.max_running_instances)))
    run(["systemctl", "enable", "--now", "android-fleet-monitor.service"])
    print("Fleet prepared: 01–04, native 1344x2992, SwANGLE, guest Vulkan disabled.")
    print("Data preserved. Start with: sudo androidctl fleet start")


def snapshot(cfg, ident):
    try:
        obj = get_instance(cfg, ident)
        props = systemd.properties(ident)
        return {
            "id": ident,
            "state": props.get("ActiveState", "unknown"),
            "substate": props.get("SubState", "unknown"),
            "pid": props.get("MainPID", "0"),
            "restarts": props.get("NRestarts", "0"),
            "result": props.get("Result", "unknown"),
            "exit_status": props.get("ExecMainStatus", ""),
            "proxy_active": systemd.active(ident, "adb-proxy"),
            "remote_port": obj.remote_adb_port,
        }
    except (Error, OSError, ValueError) as exc:
        return {"id": ident, "state": "unavailable", "error": str(exc)}


def monitor(cfg):
    require_root()
    logger = logging.getLogger("androidctl.fleet")
    logger.setLevel(logging.INFO)
    path = Path(cfg.log_root) / "fleet.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=5)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    previous = {}
    last_heartbeat = 0.0
    while True:
        now = time.monotonic()
        heartbeat = now - last_heartbeat >= 60
        for ident in IDS:
            row = snapshot(cfg, ident)
            changed = previous.get(ident) != row
            if changed or heartbeat:
                event = {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "event": "state_change" if changed else "heartbeat",
                    **row,
                }
                logger.info(json.dumps(event, sort_keys=True))
                print(json.dumps(event, sort_keys=True), flush=True)
            previous[ident] = row
        if heartbeat:
            last_heartbeat = now
        time.sleep(10)


def dispatch(cfg, args):
    action = args.action
    if action == "setup":
        setup(cfg, args.api)
        return 0
    if action == "_monitor":
        monitor(cfg)
        return 0
    if action == "watch":
        return run(
            ["journalctl", "-u", "android-fleet-monitor.service", "-n", "40", "-f", "-o", "cat"],
            capture=False,
            timeout=None,
            check=False,
        ).returncode
    ids = selected(args.ids)
    objects = [get_instance(cfg, i) for i in ids]  # Validate all before mutation.
    if action in ("start", "stop", "restart", "enable", "disable"):
        require_root()
        with lock(cfg):
            if action in ("start", "restart"):
                for obj in objects:
                    systemd.gpu_policy(obj)
                    if systemd.properties(obj.id).get("ActiveState") == "failed":
                        systemd.action("reset-failed", obj.id)
            units = [systemd.unit(i) for i in ids]
            command = ["systemctl", action]
            if action in ("start", "stop", "restart"):
                command.append("--no-block")
            run(command + units)
            if action in ("enable", "disable"):
                for obj in objects:
                    save(
                        Path(cfg.instance_root) / f"{obj.id}.conf",
                        replace(obj, autostart=action == "enable"),
                        "instance",
                    )
        print(f"{action}: {', '.join(ids)} submitted. Check androidctl fleet status.")
        return 0
    running = 0
    for obj in objects:
        view = health.status(cfg, obj)
        running += view["state"] == "running"
        if action == "screen":
            endpoint = view["endpoint"]
            print(f"# Device {obj.id}: run on your Windows client")
            print(f"adb connect {endpoint}")
            print(f"scrcpy -s {endpoint} --no-audio --video-codec=h264 --max-fps=30")
        else:
            props = systemd.properties(obj.id)
            print(
                f"{obj.id} {view['state']:10} {view['health']:9} "
                f"pid={view['pid']} restarts={props.get('NRestarts', '0')} "
                f"endpoint={view['endpoint']} native_pixel={obj.native_pixel_display}"
            )
    if action == "status":
        print(f"Running: {running}/{len(objects)} (running means boot completed).")
    return 0
