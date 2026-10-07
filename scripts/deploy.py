#!/usr/bin/env python3
"""Host deployment only; never run by unit tests or ordinary CLI commands."""

import argparse
import grp
import hashlib
import os
import platform
import pwd
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from androidctl import systemd  # noqa: E402
from androidctl.config import instances, load, save  # noqa: E402
from androidctl.errors import Error  # noqa: E402
from androidctl.sdk import SDK  # noqa: E402
from androidctl.util import atomic_write, lock, require_root, run  # noqa: E402

CONFIG = Path("/etc/androidctl/androidctl.conf")


def assert_stopped(cfg):
    for obj in instances(cfg):
        if systemd.properties(obj.id).get("ActiveState") not in ("inactive", "failed"):
            raise Error(f"Stop instance {obj.id} before installation/upgrade/uninstall.")


def copy_application(cfg, account):
    destination = Path("/usr/local/lib/androidctl")
    destination.mkdir(parents=True, exist_ok=True)
    staging = destination / "androidctl.new"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.copytree(REPO / "src/androidctl", staging, ignore=shutil.ignore_patterns("__pycache__"))
    previous = destination / "androidctl.previous"
    if previous.exists():
        shutil.rmtree(previous)
    current = destination / "androidctl"
    if current.exists():
        current.rename(previous)
    staging.rename(current)
    shutil.copy2(REPO / "libexec/androidctl", "/usr/local/bin/androidctl")
    os.chmod("/usr/local/bin/androidctl", 0o755)
    values = {
        "SERVICE_USER": cfg.service_user,
        "SERVICE_GROUP": grp.getgrgid(account.pw_gid).gr_name,
        "SERVICE_HOME": cfg.service_home,
        "AVD_ROOT": cfg.avd_root,
        "RUNTIME_ROOT": cfg.runtime_root,
        "START_TIMEOUT": str(cfg.boot_timeout + 60),
        "STOP_TIMEOUT": str(cfg.stop_timeout + 40),
    }
    for template in (REPO / "systemd").glob("*.service"):
        text = template.read_text()
        for key, value in values.items():
            text = text.replace(f"@{key}@", value)
        atomic_write(Path("/etc/systemd/system") / template.name, text)
    atomic_write("/etc/tmpfiles.d/androidctl.conf", f"d {cfg.runtime_root} 0755 root root -\n")
    run(["systemd-tmpfiles", "--create", "/etc/tmpfiles.d/androidctl.conf"])
    run(["systemctl", "daemon-reload"])
    for obj in instances(cfg):
        systemd.gpu_policy(obj)


def bootstrap_sdk(cfg):
    sdk = Path(cfg.sdk_root)
    target = sdk / "cmdline-tools" / cfg.cmdline_tools_version
    if not (target / "bin/sdkmanager").exists():
        with tempfile.TemporaryDirectory(prefix="androidctl-download-") as temp:
            archive = Path(temp) / "tools.zip"
            url = f"https://dl.google.com/android/repository/commandlinetools-linux-{cfg.cmdline_tools_version}_latest.zip"
            print(f"Downloading {url}", flush=True)
            urllib.request.urlretrieve(url, archive)
            with archive.open("rb") as downloaded:
                hasher = hashlib.sha256()
                for chunk in iter(lambda: downloaded.read(1024 * 1024), b""):
                    hasher.update(chunk)
                digest = hasher.hexdigest()
            if digest.lower() != cfg.cmdline_tools_sha256.lower():
                raise Error("Official command-line tools SHA-256 mismatch; refusing installation.")
            with zipfile.ZipFile(archive) as z:
                for entry in z.infolist():
                    parts = Path(entry.filename).parts
                    if entry.filename.startswith("/") or ".." in parts:
                        raise Error("Unsafe archive member.")
                z.extractall(temp)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(Path(temp) / "cmdline-tools"), target)
            for binary in (target / "bin").iterdir():
                binary.chmod(0o755)
    latest = sdk / "cmdline-tools/latest"
    if latest.exists() and not latest.is_symlink():
        # Respect an existing administrator-managed installation.
        print(f"Using existing directory {latest}; pinned download retained at {target}")
    else:
        latest.unlink(missing_ok=True)
        latest.symlink_to(target.name)


def install(args, upgrade=False):
    cfg = load(CONFIG)
    if args.user:
        if CONFIG.exists() and args.user != cfg.service_user:
            raise Error("Changing service identity requires explicit offline ownership migration.")
        cfg = replace(cfg, service_user=args.user).validate()
    if platform.machine() != "x86_64":
        raise Error("This release supports x86_64 only.")
    release = platform.freedesktop_os_release()
    if release.get("ID") != "ubuntu" or release.get("VERSION_ID") != "24.04":
        raise Error("First supported target: Ubuntu 24.04 LTS. Other releases require validation.")
    if not Path("/run/systemd/system").is_dir() or not Path("/dev/kvm").exists():
        raise Error("A booted systemd host with /dev/kvm is required. Enable VT-x/AMD-V first.")
    if not any(flag in Path("/proc/cpuinfo").read_text().split() for flag in ("vmx", "svm")):
        raise Error("CPU virtualization extensions not exposed.")
    with lock(cfg):
        assert_stopped(cfg)
        run(["apt-get", "update"], capture=False, timeout=None)
        run(
            [
                "apt-get",
                "install",
                "-y",
                "python3",
                "openjdk-21-jre-headless",
                "ca-certificates",
                "socat",
                "pciutils",
                "iproute2",
                "mesa-utils",
                "libegl1",
                "libgl1",
                "libgl1-mesa-dri",
                "libpulse0",
                "libnss3",
                "libx11-6",
                "libxcb1",
                "libxkbcommon0",
                "libasound2t64",
                "unzip",
            ],
            capture=False,
            timeout=None,
        )
        try:
            account = pwd.getpwnam(cfg.service_user)
        except KeyError:
            run(
                [
                    "useradd",
                    "--system",
                    "--user-group",
                    "--home-dir",
                    cfg.service_home,
                    "--shell",
                    "/usr/sbin/nologin",
                    cfg.service_user,
                ]
            )
            account = pwd.getpwnam(cfg.service_user)
        if account.pw_uid == 0:
            raise Error("Service account must not be root.")
        groups = []
        for group in ("kvm", "render", "video"):
            try:
                grp.getgrnam(group)
                groups.append(group)
            except KeyError:
                if group == "kvm":
                    raise Error("The host lacks the kvm group. Fix /dev/kvm udev ownership first.") from None
        run(["usermod", "-a", "-G", ",".join(groups), cfg.service_user])
        for value in (cfg.service_home, cfg.avd_root, cfg.log_root):
            path = Path(value)
            path.mkdir(parents=True, exist_ok=True)
            os.chown(path, account.pw_uid, account.pw_gid)
            path.chmod(0o750)
        Path(cfg.instance_root).mkdir(parents=True, exist_ok=True)
        Path(cfg.sdk_root).mkdir(parents=True, exist_ok=True)
        if not CONFIG.exists():
            save(CONFIG, cfg)
        if not upgrade:
            bootstrap_sdk(cfg)
            sdk = SDK(cfg)
            sdk.licenses(args.accept_licenses)
            sdk.install(["emulator", "platform-tools"])
        copy_application(cfg, account)
        # Apply any managed ADB port/identity changes while no emulators run.
        run(["systemctl", "stop", "android-adb.service"], check=False)
    print("Installed. AVD data and instance configuration preserved. No devices enabled automatically.")
    print(
        "Next: sudo androidctl doctor; androidctl profiles; sudo androidctl create 01 --api 35 --profile pixel_8_pro --install-image"
    )
    print("Existing login sessions need a logout/login to pick up newly added groups.")
    result = run(["/usr/local/bin/androidctl", "doctor"], capture=False, check=False)
    return result.returncode


def uninstall(args):
    cfg = load(CONFIG, required=True)
    with lock(cfg):
        assert_stopped(cfg)
        print(
            "Remove androidctl code, unit templates, device policies, tmpfiles rule. Keep configuration, SDK, account and AVD data by default."
        )
        if args.purge:
            print(
                f"PURGE also removes registered AVDs in {cfg.avd_root}, their instance configs in {cfg.instance_root}, and {CONFIG}; SDK, service home/account remain to avoid deleting unrelated files."
            )
            if not args.yes and (not sys.stdin.isatty() or input("Type PURGE to confirm: ") != "PURGE"):
                raise Error("Purge declined; use --purge --yes for explicit noninteractive deletion.", 11)
        for obj in instances(cfg):
            systemd.action("disable", obj.id)
            systemd.remove_policy(obj.id)
        run(["systemctl", "stop", "android-adb.service"], check=False)
        for name in ("android-emulator@.service", "android-adb-proxy@.service", "android-adb.service"):
            (Path("/etc/systemd/system") / name).unlink(missing_ok=True)
        Path("/usr/local/bin/androidctl").unlink(missing_ok=True)
        shutil.rmtree("/usr/local/lib/androidctl", ignore_errors=True)
        Path("/etc/tmpfiles.d/androidctl.conf").unlink(missing_ok=True)
        if args.purge:
            # Only known managed AVDs, not arbitrary contents under custom roots.
            from androidctl import avd

            for obj in instances(cfg):
                avd.remove(cfg, obj)
                (Path(cfg.instance_root) / f"{obj.id}.conf").unlink()
            CONFIG.unlink()
        run(["systemctl", "daemon-reload"])
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("install", "upgrade", "uninstall"))
    parser.add_argument("--user")
    parser.add_argument("--accept-licenses", action="store_true")
    parser.add_argument("--purge", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    try:
        require_root()
        return uninstall(args) if args.mode == "uninstall" else install(args, args.mode == "upgrade")
    except (Error, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return getattr(exc, "code", 5)


if __name__ == "__main__":
    raise SystemExit(main())
