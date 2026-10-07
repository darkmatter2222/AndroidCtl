import argparse
import json
import sys
from dataclasses import asdict

from . import __version__, adb, gpu, health, host, instance, service, systemd
from .config import Config, convert, get_instance, instances, load, save
from .errors import Error
from .sdk import SDK
from .util import lock, require_root, run


def parser():
    p = argparse.ArgumentParser(
        prog="androidctl", description="Persistent Android virtual devices on native Ubuntu/KVM."
    )
    p.add_argument("--config", default="/etc/androidctl/androidctl.conf")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("version")
    sub.add_parser("doctor").add_argument("--json", action="store_true")
    for name in ("list", "ports", "profiles"):
        sub.add_parser(name).add_argument("--json", action="store_true")
    for name in ("status", "info", "health", "adb-endpoint"):
        s = sub.add_parser(name)
        s.add_argument("id", nargs="?" if name == "status" else None)
        s.add_argument("--json", action="store_true")
    c = sub.add_parser("create")
    c.add_argument("id")
    for name in ("api", "ram", "cpus", "console-port", "remote-adb-port"):
        c.add_argument("--" + name, type=int)
    for name in ("profile", "image", "name", "disk", "gpu", "gpu-pci"):
        c.add_argument("--" + name)
    c.add_argument("--architecture", default="x86_64")
    c.add_argument("--install-image", action="store_true")
    c.add_argument("--start", action="store_true")
    for name in ("start", "stop", "restart", "enable", "disable", "delete", "logs", "shell", "adb"):
        s = sub.add_parser(name)
        s.add_argument("id")
        if name in ("start", "restart"):
            s.add_argument("--force", action="store_true")
        if name == "delete":
            s.add_argument("--yes", action="store_true")
            s.add_argument("--keep-data", action="store_true")
        if name == "logs":
            s.add_argument("--follow", action="store_true")
            s.add_argument("--since")
        if name == "adb":
            s.add_argument("args", nargs=argparse.REMAINDER)
    sdk = sub.add_parser("sdk").add_subparsers(dest="action", required=True)
    for name in ("status", "images", "update"):
        sdk.add_parser(name)
    s = sdk.add_parser("install-image")
    s.add_argument("--api", type=int, required=True)
    s.add_argument("--image", default="google_apis")
    s = sdk.add_parser("licenses")
    s.add_argument("--accept", action="store_true")
    sub.add_parser("gpu").add_subparsers(dest="action", required=True).add_parser("list").add_argument(
        "--json", action="store_true"
    )
    config = sub.add_parser("config").add_subparsers(dest="action", required=True)
    config.add_parser("show")
    config.add_parser("get").add_argument("key")
    s = config.add_parser("set")
    s.add_argument("key")
    s.add_argument("value")
    s = sub.add_parser("_service", help="internal systemd entry points")
    s.add_argument(
        "action", choices=("preflight", "launch", "postboot", "stop", "release", "proxy", "adb-server")
    )
    s.add_argument("id", nargs="?")
    return p


def output(value, as_json=False):
    if as_json or isinstance(value, dict):
        print(json.dumps(value, indent=2))
    elif isinstance(value, list):
        if not value:
            print("No entries.")
        elif isinstance(value[0], dict):
            keys = list(value[0])
            widths = {k: max(len(k), *(len(str(r.get(k, ""))) for r in value)) for k in keys}
            print("  ".join(k.upper().ljust(widths[k]) for k in keys))
            for row in value:
                print("  ".join(str(row.get(k, "")).ljust(widths[k]) for k in keys))
        else:
            print("\n".join(str(v) for v in value))
    else:
        print(value)


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if not args.command:
        p.print_help()
        return 0
    try:
        if args.command == "version":
            print(__version__)
            return 0
        cfg = load(args.config)
        cmd = args.command
        if cmd == "_service":
            if args.config != "/etc/androidctl/androidctl.conf":
                raise Error("Systemd helpers require the installed configuration.")
            if args.action == "adb-server":
                service.adb_server(cfg)
            else:
                obj = get_instance(cfg, args.id)
                fn = {"stop": service.graceful_stop}.get(args.action, getattr(service, args.action, None))
                fn(cfg, obj)
            return 0
        if cmd == "doctor":
            rows = host.doctor(cfg)
            output(rows, args.json)
            return 5 if any(r["status"] == "FAIL" for r in rows) else 0
        if cmd == "gpu":
            output(gpu.discover(), args.json)
        elif cmd == "profiles":
            output(SDK(cfg).profiles(), args.json)
        elif cmd == "config":
            data = asdict(cfg)
            if args.action == "show":
                output(data)
            elif args.key not in data:
                raise Error(f"Unknown setting {args.key}")
            elif args.action == "get":
                output(data[args.key])
            else:
                require_root()
                # Path/user changes require reinstalling rendered unit definitions.
                immutable = {
                    "sdk_root",
                    "avd_root",
                    "instance_root",
                    "runtime_root",
                    "service_user",
                    "service_home",
                    "boot_timeout",
                    "stop_timeout",
                }
                if args.key in immutable:
                    raise Error(
                        "This setting is rendered into installed services. Stop devices, edit the config, then run upgrade.sh; paths require manual data migration."
                    )
                with lock(cfg):
                    if any(
                        systemd.properties(i.id).get("ActiveState") not in ("inactive", "failed")
                        for i in instances(cfg)
                    ):
                        raise Error("Stop all managed instances before changing global configuration.")
                    data[args.key] = args.value
                    updated = convert(Config, data)
                    save(args.config, updated)
                print(
                    "Saved. Existing instance CPU/RAM/GPU/ports remain fixed. Restart the managed ADB service if its port changed."
                )
        elif cmd == "sdk":
            sdk = SDK(cfg)
            if args.action == "status":
                kind, command = sdk.backend()
                output({"backend": kind, "command": command, "sdk_root": cfg.sdk_root})
            elif args.action == "images":
                output(sdk.images())
            else:
                require_root()
                with lock(cfg):
                    if any(
                        systemd.properties(i.id).get("ActiveState") not in ("inactive", "failed")
                        for i in instances(cfg)
                    ):
                        raise Error("Stop managed emulators before SDK changes.")
                    if args.action == "update":
                        sdk.update()
                    elif args.action == "licenses":
                        sdk.licenses(args.accept)
                    else:
                        package = f"system-images;android-{args.api};{args.image};x86_64"
                        if package not in sdk.images():
                            raise Error("Requested image is unavailable; inspect androidctl sdk images.", 8)
                        sdk.install([package])
        elif cmd in ("list", "ports") or (cmd == "status" and args.id is None):
            rows = []
            for obj in instances(cfg):
                if cmd == "ports":
                    rows.append(
                        {
                            k: getattr(obj, k)
                            for k in ("id", "console_port", "local_adb_port", "remote_adb_port")
                        }
                    )
                else:
                    view = health.status(cfg, obj)
                    rows.append(
                        view
                        if args.json
                        else {
                            k: view[k]
                            for k in (
                                "id",
                                "name",
                                "api",
                                "state",
                                "health",
                                "endpoint",
                                "cpu_cores",
                                "ram_mb",
                            )
                        }
                    )
            output(rows, args.json)
        elif cmd == "create":
            require_root()
            obj = instance.create(cfg, args)
            output(asdict(obj))
            if args.start:
                output(instance.start(cfg, obj))
        else:
            obj = get_instance(cfg, args.id)
            if cmd in ("start", "stop", "restart", "enable", "disable", "delete"):
                require_root()
                if cmd in ("stop", "restart"):
                    instance.stop(cfg, obj)
                if cmd in ("start", "restart"):
                    output(instance.start(cfg, obj, args.force))
                elif cmd in ("enable", "disable"):
                    instance.enable(cfg, obj, cmd == "enable")
                elif cmd == "delete":
                    instance.delete(cfg, obj, args.yes, args.keep_data)
            elif cmd in ("status", "info", "health"):
                view = health.status(cfg, obj)
                output(view, args.json)
                if cmd == "health" and view["health"] != "healthy":
                    return 10
            elif cmd == "adb-endpoint":
                print(health.status(cfg, obj)["endpoint"])
            elif cmd in ("adb", "shell"):
                return adb.command(
                    cfg,
                    obj,
                    ["shell"] if cmd == "shell" else args.args,
                    check=False,
                    capture=False,
                    timeout=None,
                ).returncode
            elif cmd == "logs":
                command = ["journalctl", "-u", systemd.unit(obj.id), "-u", systemd.unit(obj.id, "adb-proxy")]
                if args.follow:
                    command.append("--follow")
                if args.since:
                    since = args.since
                    if since.endswith("m") and since[:-1].isdigit():
                        since = f"{since[:-1]} minutes ago"
                    command.extend(["--since", since])
                return run(command, capture=False, timeout=None, check=False).returncode
        return 0
    except Error as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.code
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 5
    except KeyboardInterrupt:
        print(
            "Interrupted. Check status: systemd operations already submitted may continue.", file=sys.stderr
        )
        return 130
