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
    if device and device["driver"] == "nvidia":
        # EGL vendor selection is not reliable per PCI on multi-NVIDIA hosts.
        if len([d for d in discover() if d["driver"] == "nvidia"]) != 1:
            raise Error("NVIDIA rendering currently requires a single NVIDIA GPU host.", 5)
        info = Path("/proc/driver/nvidia/gpus") / pci / "information"
        try:
            import re

            match = re.search(r"Device Minor:\s*(\d+)", info.read_text())
            if not match:
                raise ValueError("missing NVIDIA device minor")
            node = f"/dev/nvidia{int(match[1])}"
            required = [node, "/dev/nvidiactl"]
            if not all(Path(n).exists() for n in required):
                raise ValueError("missing NVIDIA device nodes")
        except (OSError, ValueError) as exc:
            raise Error(f"NVIDIA device setup unavailable: {exc}", 5) from exc
        optional = ["/dev/nvidia-modeset", "/dev/nvidia-uvm", "/dev/nvidia-uvm-tools"]
        return {**device, "nodes": device["nodes"] + required + [n for n in optional if Path(n).exists()]}
    if not device or not device["render_node"]:
        raise Error(f"Selected GPU {pci} has no render node.", 5)
    if device["driver"] not in ("i915", "xe", "amdgpu", "radeon", "nouveau"):
        raise Error(
            "Unsupported GPU driver. Use supported Mesa or single-NVIDIA host rendering, or choose software.",
            5,
        )
    return device


def environment(instance):
    dev = selection(instance)
    if not dev:
        return {"LIBGL_ALWAYS_SOFTWARE": "1"}
    if dev["driver"] == "nvidia":
        env = {
            "__GLX_VENDOR_LIBRARY_NAME": "nvidia",
            "__VK_LAYER_NV_optimus": "NVIDIA_only",
        }
        vendor = Path("/usr/share/glvnd/egl_vendor.d/10_nvidia.json")
        if vendor.exists():
            env["__EGL_VENDOR_LIBRARY_FILENAMES"] = str(vendor)
        return env
    selector = "pci-" + dev["pci"].replace(":", "_").replace(".", "_")
    return {"DRI_PRIME": selector, "MESA_VK_DEVICE_SELECT_FORCE_DEFAULT_DEVICE": "1"}


def configure(cfg, obj, mode, pci="auto"):
    """Change only a stopped instance's renderer; keep userdata and Vulkan policy."""
    from dataclasses import replace

    from . import systemd
    from .config import save
    from .util import lock

    with lock(cfg):
        if systemd.properties(obj.id).get("ActiveState") not in ("inactive", "failed"):
            raise Error("Stop the instance before changing its renderer.")
        if mode == "host" and pci == "auto":
            candidates = [d for d in discover() if d["driver"] == "nvidia"]
            if not candidates:
                candidates = [
                    d
                    for d in discover()
                    if d["render_node"] and d["driver"] in ("i915", "xe", "amdgpu", "radeon", "nouveau")
                ]
            if len(candidates) != 1:
                raise Error(
                    "Automatic selection requires exactly one NVIDIA GPU or one Mesa GPU; specify --gpu-pci."
                )
            pci = candidates[0]["pci"]
        updated = replace(obj, gpu_mode=mode, gpu_pci=pci if mode == "host" else "").validate()
        selection(updated)
        path = Path(cfg.instance_root) / f"{obj.id}.conf"
        if path.exists():
            backup = path.with_suffix(".conf.before-renderer")
            if not backup.exists():
                from .util import atomic_write

                atomic_write(backup, path.read_text(), 0o600)
        systemd.gpu_policy(updated)
        save(path, updated, "instance")
    return {
        "id": obj.id,
        "gpu_mode": updated.gpu_mode,
        "gpu_pci": updated.gpu_pci,
        "message": "Renderer saved; start this instance and validate GPU use. Userdata preserved.",
    }
