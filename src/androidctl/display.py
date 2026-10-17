"""Persistent instance display policy, reapplied after every service boot."""

import re
from dataclasses import replace
from pathlib import Path

from . import adb, systemd
from .config import save
from .errors import Error
from .util import lock

SCALES = (25, 33, 50, 75, 100)


def apply(cfg, obj):
    scale = obj.display_scale
    if not scale:
        return
    size = adb.command(cfg, obj, ["shell", "wm", "size"]).stdout
    density = adb.command(cfg, obj, ["shell", "wm", "density"]).stdout
    match = re.search(r"Physical size: (\d+)x(\d+)", size)
    dpi = re.search(r"Physical density: (\d+)", density)
    if not match or not dpi:
        raise Error("Could not read physical display size/density; policy remains saved.")
    dimensions = [max(2, round(int(v) * scale / 200) * 2) for v in match.groups()]
    target_size = "reset" if scale == 100 else "x".join(map(str, dimensions))
    target_dpi = "reset" if scale == 100 else str(max(72, round(int(dpi[1]) * scale / 100)))
    adb.command(cfg, obj, ["shell", "wm", "size", target_size])
    adb.command(cfg, obj, ["shell", "wm", "density", target_dpi])


def configure(cfg, obj, scale):
    if scale not in SCALES:
        raise Error("Display scale must be 25, 33, 50, 75, or 100.")
    with lock(cfg):
        state = systemd.properties(obj.id).get("ActiveState")
        if state in ("activating", "deactivating"):
            raise Error("Wait for the instance to finish starting or stopping.")
        updated = replace(obj, display_scale=scale)
        save(Path(cfg.instance_root) / f"{obj.id}.conf", updated, "instance")
        if state == "active":
            adb.connect(cfg, updated)
            apply(cfg, updated)
    return updated
