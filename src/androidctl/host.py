import grp
import ipaddress
import json
import os
import platform
import pwd
import socket
from pathlib import Path

from .errors import Error
from .gpu import discover
from .sdk import SDK, environment
from .util import run


def bind_address(cfg):
    if cfg.bind_address != "auto":
        return cfg.bind_address
    routes = json.loads(run(["ip", "-j", "route", "get", "1.1.1.1"]).stdout)
    address = routes[0].get("prefsrc", "") if routes else ""
    from dataclasses import replace

    replace(cfg, bind_address=address).validate()
    if ipaddress.ip_address(address).is_loopback:
        raise Error("auto did not find a LAN address; configure bind_address explicitly.", 5)
    return address


def available_ram():
    fields = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    return int(fields["MemAvailable"].split()[0]) // 1024


def check_kvm():
    if platform.machine() != "x86_64" or not Path("/dev/kvm").exists():
        raise Error("Native x86_64 KVM (/dev/kvm) is required; enable VT-x/AMD-V in firmware.", 5)


def doctor(cfg):
    rows = []

    def check(name, fn, remedy, warning=False):
        try:
            result = fn()
            ok = bool(result)
            rows.append(
                {
                    "check": name,
                    "status": "PASS" if ok else ("WARN" if warning else "FAIL"),
                    "detail": str(result) if ok else remedy,
                }
            )
        except (Error, OSError, KeyError, ValueError) as exc:
            rows.append(
                {"check": name, "status": "WARN" if warning else "FAIL", "detail": f"{remedy}: {exc}"}
            )

    def tool(args, service=False):
        prefix = ["runuser", "-u", cfg.service_user, "--"] if service and os.geteuid() == 0 else []
        p = run(prefix + args, env=environment(cfg), check=False, timeout=20)
        return p.stdout.strip() or True if p.returncode == 0 else False

    check("OS", lambda: platform.freedesktop_os_release().get("ID") == "ubuntu", "Use Ubuntu 24.04 LTS.")
    check("architecture", lambda: platform.machine() == "x86_64", "Use x86_64.")
    check(
        "CPU virtualization",
        lambda: any(f in Path("/proc/cpuinfo").read_text().split() for f in ("vmx", "svm")),
        "Enable VT-x/AMD-V.",
    )
    check("KVM", lambda: Path("/dev/kvm").exists(), "Enable virtualization / nested KVM if applicable.")
    check(
        "KVM modules",
        lambda: (
            Path("/sys/module/kvm").exists()
            and any(Path("/sys/module", n).exists() for n in ("kvm_intel", "kvm_amd"))
        ),
        "Load the appropriate host KVM module.",
    )

    def membership():
        account = pwd.getpwnam(cfg.service_user)
        return grp.getgrnam("kvm").gr_gid in os.getgrouplist(account.pw_name, account.pw_gid)

    check("service user kvm group", membership, "Run installer to grant KVM access.")
    check(
        "KVM acceleration",
        lambda: tool([SDK(cfg).tool("emulator"), "-accel-check"], True),
        "Run doctor with sudo to check the service identity; inspect /dev/kvm permissions.",
    )
    for name in ("adb", "emulator", "avdmanager", "sdkmanager"):
        check(name, lambda n=name: SDK(cfg).tool(n), "Run installer.")
    check("Java", lambda: tool(["java", "-version"]), "Install openjdk-21-jre-headless.")
    check("systemd", lambda: Path("/run/systemd/system").exists(), "Boot a systemd host.")
    check("socat", lambda: tool(["socat", "-V"]), "Install socat.")
    check("GPU devices", discover, "No physical GPU detected; software rendering is supported.", True)
    check(
        "EGL",
        lambda: tool(["eglinfo", "-B"], True),
        "Host rendering may need working Mesa/EGL; use software rendering.",
        True,
    )
    check(
        "OpenGL",
        lambda: tool(["glxinfo", "-B"], True),
        "GLX may be absent on a headless host; inspect EGL/emulator logs.",
        True,
    )
    for name in ("instance_root", "avd_root"):
        check(name, lambda n=name: Path(getattr(cfg, n)).is_dir(), "Run installer.")
    check("bind address", lambda: bind_address(cfg), "Configure a local interface address.")
    check("hostname", socket.gethostname, "Check host name resolution.")
    return rows
