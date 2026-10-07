from pathlib import Path

from .errors import Error
from .util import run


def discover():
    result = []
    for dev in sorted(Path("/sys/bus/pci/devices").glob("*")):
        try:
            if not (dev / "class").read_text().strip().startswith("0x03"):
                continue
            driver = (dev / "driver").resolve().name if (dev / "driver").exists() else "none"
            nodes = sorted(str(Path("/dev/dri") / n.name) for n in (dev / "drm").glob("renderD*"))
            cards = sorted(str(Path("/dev/dri") / n.name) for n in (dev / "drm").glob("card[0-9]*"))
            name = run(["lspci", "-s", dev.name], check=False).stdout.strip()
            result.append(
                {
                    "index": len(result),
                    "pci": dev.name,
                    "driver": driver,
                    "render_node": nodes[0] if nodes else "",
                    "nodes": nodes + cards,
                    "device": name,
                }
            )
        except (OSError, Error):
            continue
    return result


def selection(instance):
    if instance.gpu_mode not in ("host", "auto"):
        return None
    pci = instance.gpu_pci
    if not pci and instance.dri_prime.startswith("pci-"):
        parts = instance.dri_prime[4:].split("_")
        pci = f"{parts[0]}:{parts[1]}:{parts[2]}.{parts[3]}"
    if not pci:
        raise Error(
            "Hardware/auto rendering requires --gpu-pci or a stable dri_prime selector; use software to avoid physical GPUs.",
            5,
        )
    device = next((d for d in discover() if d["pci"] == pci), None)
    if not device or not device["render_node"]:
        raise Error(f"Selected GPU {pci} has no render node.", 5)
    if device["driver"] not in ("i915", "xe", "amdgpu", "radeon", "nouveau"):
        raise Error(
            "v1 physical GPU selection supports Mesa drivers only; proprietary NVIDIA is not automatically used. Choose software.",
            5,
        )
    return device


def environment(instance):
    dev = selection(instance)
    if not dev:
        return {"LIBGL_ALWAYS_SOFTWARE": "1"}
    selector = "pci-" + dev["pci"].replace(":", "_").replace(".", "_")
    return {"DRI_PRIME": selector, "MESA_VK_DEVICE_SELECT_FORCE_DEFAULT_DEVICE": "1"}
