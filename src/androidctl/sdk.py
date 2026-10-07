"""Capability-detected current Android CLI with sdkmanager fallback."""

import os
import re
from pathlib import Path

from .errors import Error
from .util import run


def environment(cfg):
    env = os.environ.copy()
    # Do not inherit another user's SDK, ADB server, graphics selection or keys.
    for key in list(env):
        if key.startswith(("ANDROID_", "ADB_", "DRI_", "__NV_", "VK_", "MESA_", "LIBGL_")):
            env.pop(key)
    env.update(
        HOME=cfg.service_home,
        ANDROID_HOME=cfg.sdk_root,
        ANDROID_SDK_ROOT=cfg.sdk_root,
        ANDROID_AVD_HOME=cfg.avd_root,
        ANDROID_USER_HOME=str(Path(cfg.service_home) / ".android"),
        ADB_SERVER_SOCKET=f"tcp:{cfg.adb_server_port}",
        ANDROID_ADB_SERVER_PORT=str(cfg.adb_server_port),
        ADB_LOCAL_TRANSPORT_MAX_PORT="5683",
        QT_QPA_PLATFORM="offscreen",
    )
    return env


class SDK:
    def __init__(self, cfg):
        self.cfg = cfg
        self.env = environment(cfg)
        if os.geteuid() == 0:
            # Root package administration must not create root-owned preferences
            # in the non-root emulator account's Android home.
            admin = str(Path(cfg.sdk_root) / ".androidctl-admin")
            self.env.update(HOME=admin, ANDROID_USER_HOME=admin + "/.android")

    def tool(self, name):
        sub = {"emulator": "emulator", "adb": "platform-tools"}.get(name, "cmdline-tools/latest/bin")
        path = Path(self.cfg.sdk_root) / sub / name
        if not path.is_file():
            raise Error(f"Missing {path}; run installer or install the required SDK package.", 5)
        return str(path)

    def backend(self):
        candidate = Path(self.cfg.android_cli)
        if candidate.is_file():
            p = run(
                [candidate, f"--sdk={self.cfg.sdk_root}", "sdk", "list", "--help"],
                env=self.env,
                check=False,
                timeout=15,
            )
            if p.returncode == 0:
                return "android", [str(candidate), f"--sdk={self.cfg.sdk_root}", "sdk"]
        return "sdkmanager", [self.tool("sdkmanager"), f"--sdk_root={self.cfg.sdk_root}"]

    @staticmethod
    def package_arg(package, backend):
        return package.replace(";", "/") if backend == "android" else package

    def packages(self):
        kind, command = self.backend()
        options = ["list", "--all"] if kind == "android" else ["--list"]
        return run(command + options, env=self.env, timeout=180).stdout

    def images(self):
        text = self.packages().replace("/", ";")
        return sorted(set(re.findall(r"system-images;android-\d+;[\w.-]+;x86_64", text)))

    def installed(self, package):
        directory = Path(self.cfg.sdk_root).joinpath(*package.split(";"))
        return (directory / "package.xml").is_file() or (directory / "source.properties").is_file()

    def install(self, packages):
        kind, command = self.backend()
        args = [self.package_arg(p, kind) for p in packages]
        run(
            command + (["install"] if kind == "android" else ["--install"]) + args,
            env=self.env,
            timeout=None,
            capture=False,
        )

    def licenses(self, accept=False):
        # New CLI prompts at install. The bundled fallback supplies a documented
        # license review interface; never invent an unsupported android sdk flag.
        args = [self.tool("sdkmanager"), f"--sdk_root={self.cfg.sdk_root}", "--licenses"]
        run(args, env=self.env, timeout=None, capture=False, **({"input": "y\n" * 200} if accept else {}))

    def update(self):
        kind, command = self.backend()
        run(
            command + (["update"] if kind == "android" else ["--update"]),
            env=self.env,
            timeout=None,
            capture=False,
        )

    def profiles(self):
        text = run([self.tool("avdmanager"), "list", "device"], env=self.env).stdout
        result = []
        for block in re.split(r"\n(?=id:)", text):
            ident = re.search(r'id:\s*\d+\s+or\s+"([^"\n]+)"', block)
            name = re.search(r"Name:\s*(.+)", block)
            if ident:
                result.append(
                    {"id": ident.group(1), "name": name.group(1).strip() if name else ident.group(1)}
                )
        return result
