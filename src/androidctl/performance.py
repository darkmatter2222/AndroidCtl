"""Read-only host evidence; no process killing or driver changes."""

import os
from dataclasses import asdict
from pathlib import Path

from . import gpu, systemd
from .config import instances
from .errors import Error
from .sdk import SDK
from .util import run


def report(cfg):
    def probe(args):
        try:
            p = run(args, check=False, timeout=15)
            return {"returncode": p.returncode, "stdout": p.stdout[-16000:], "stderr": p.stderr[-4000:]}
        except (Error, OSError) as exc:
            return {"error": str(exc)}

    rows = []
    for obj in instances(cfg):
        rows.append({"configuration": asdict(obj), "service": systemd.properties(obj.id)})
    return {
        "cpu_count": os.cpu_count(),
        "load_average": os.getloadavg(),
        "memory": Path("/proc/meminfo").read_text(),
        "cpu_pressure": Path("/proc/pressure/cpu").read_text()
        if Path("/proc/pressure/cpu").exists()
        else "unavailable",
        "gpus": gpu.discover(),
        "instances": rows,
        "acceleration": probe([SDK(cfg).tool("emulator"), "-accel-check"]),
        "nvidia": probe(["nvidia-smi"]),
        "nvidia_compute_processes": probe(
            ["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory", "--format=csv"]
        ),
        "processes": probe(["ps", "-eo", "pid,comm,pcpu,pmem", "--sort=-pcpu"]),
        "note": "Software SwANGLE/SwiftShader uses CPU. Host GPU mode is opt-in. No model processes were stopped.",
    }
