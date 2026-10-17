"""Allowlisted AndroidCtl host operations for the local workbench."""

import json
import os
import re
import shlex
import subprocess
import threading
from pathlib import Path


class Hosts:
    def __init__(self, state):
        self.state = Path(state)
        self.profiles = json.loads(self.state.read_text()) if self.state.exists() else {}
        self.inventory = {}
        self.jobs = {}
        self.lock = threading.RLock()

    @staticmethod
    def word(value, label):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", value):
            raise ValueError(f"Invalid {label}")
        return value

    def save(self, data):
        ident = self.word(data.get("id"), "host name")
        target = data.get("target", "")
        if target != "local" and not re.fullmatch(
            r"(?:[A-Za-z0-9_][A-Za-z0-9_.-]*@)?[A-Za-z0-9][A-Za-z0-9_.-]*", target
        ):
            raise ValueError(
                "SSH target must be user@hostname or an SSH config alias; use local for this machine"
            )
        endpoint = self.word(data.get("endpoint_host"), "ADB endpoint hostname")
        port = data.get("port", 22)
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Invalid SSH port")
        with self.lock:
            if self.jobs.get(ident, {}).get("state") == "running":
                raise ValueError("Host operation in progress")
            self.profiles[ident] = {"id": ident, "target": target, "endpoint_host": endpoint, "port": port}
            self.inventory.pop(ident, None)
            self.state.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.profiles, indent=2))
            os.replace(tmp, self.state)
        return {"message": "Host saved; scan instances to discover running and stopped devices"}

    def command(self, host, args, mutate=False):
        command = (["sudo", "-n"] if mutate else []) + ["androidctl", *args]
        if host["target"] != "local":
            command = [
                "ssh",
                "-T",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                "-o",
                "StrictHostKeyChecking=yes",
                "-p",
                str(host["port"]),
                host["target"],
                shlex.join(command),
            ]
        elif os.name == "nt":
            raise ValueError("Local instance management requires Linux; configure your Linux host over SSH")
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=600, stdin=subprocess.DEVNULL
        )
        if result.returncode:
            raise ValueError((result.stderr or result.stdout).strip()[-4000:] or "Host command failed")
        return result.stdout

    def snapshot(self):
        with self.lock:
            return [
                {**h, "operation": self.jobs.get(key), "instances": self.inventory.get(key, [])}
                for key, h in self.profiles.items()
            ]

    def action(self, data):
        action = data.get("action")
        if action == "save":
            return self.save(data)
        ident = self.word(data.get("host"), "host name")
        with self.lock:
            if ident not in self.profiles:
                raise ValueError("Unknown host")
            if self.jobs.get(ident, {}).get("state") == "running":
                raise ValueError("Host operation already in progress")
            host = dict(self.profiles[ident])
            args = ["list", "--json"]
            reports = {
                "diagnostics": ["performance", "--json"],
                "doctor": ["doctor", "--json"],
                "profiles": ["profiles", "--json"],
                "ports": ["ports", "--json"],
                "gpu-list": ["gpu", "list", "--json"],
                "config": ["config", "show"],
                "sdk-images": ["sdk", "images"],
                "sdk-status": ["sdk", "status"],
            }
            if action in reports:
                args = reports[action]
            elif action != "scan":
                instance = str(data.get("instance", ""))
                if not re.fullmatch(r"\d{1,2}", instance) or not 1 <= int(instance) <= 64:
                    raise ValueError("Instance ID must be 01–64")
                instance = f"{int(instance):02d}"
                if action not in (
                    "create",
                    "start",
                    "stop",
                    "restart",
                    "enable",
                    "disable",
                    "delete",
                    "renderer",
                    "display",
                    "logs",
                    "info",
                    "health",
                ):
                    raise ValueError("Unknown host action")
                known = self.inventory.get(ident)
                if known is None:
                    raise ValueError("Scan this host before changing instances")
                exists = any(str(row["id"]).zfill(2) == instance for row in known)
                if (action == "create") == exists:
                    raise ValueError("Instance already exists" if exists else "Instance not found; scan host")
                args = [action, instance]
                if action in ("info", "health"):
                    args.append("--json")
                if action == "logs":
                    args.extend(["--since", "30m"])
                if action == "display" or (action == "create" and "display_scale" in data):
                    scale = data.get("display_scale")
                    if type(scale) is not int or scale not in (25, 33, 50, 75, 100):
                        raise ValueError("Invalid display scale")
                    args.extend(["--scale" if action == "display" else "--display-scale", str(scale)])
                if action == "renderer":
                    mode = data.get("gpu")
                    if mode not in ("host", "swangle"):
                        raise ValueError("Unsupported renderer")
                    args.extend(["--gpu", mode])
                if action == "delete":
                    if data.get("confirm") != f"DELETE {instance}":
                        raise ValueError(f"Deletion requires exact confirmation DELETE {instance}")
                    if type(data.get("erase_data")) is not bool:
                        raise ValueError("Select whether to erase or preserve userdata")
                    args.append("--yes")
                    if not data["erase_data"]:
                        args.append("--keep-data")
                if action == "create":
                    profile = self.word(data.get("profile", "pixel_8_pro"), "hardware profile")
                    for key, default, low, high, flag in (
                        ("api", 35, 23, 99, "--api"),
                        ("ram", 4096, 512, 65536, "--ram"),
                        ("cpus", 4, 1, 64, "--cpus"),
                    ):
                        value = data.get(key, default)
                        if type(value) is not int or not low <= value <= high:
                            raise ValueError(f"Invalid {key}")
                        args.extend([flag, str(value)])
                    args.extend(["--profile", profile])
                    # Existing installed SDK images only: no unattended license acceptance/download.
            self.jobs[ident] = {"state": "running", "message": f"{action}: running on {ident}"}
            threading.Thread(target=self.worker, args=(ident, host, action, args), daemon=True).start()
        return {"message": f"{action} started; watch host status"}

    def worker(self, ident, host, action, args):
        output = ""
        try:
            if action != "scan":
                readonly = action in (
                    "diagnostics",
                    "doctor",
                    "profiles",
                    "ports",
                    "gpu-list",
                    "config",
                    "sdk-images",
                    "sdk-status",
                    "logs",
                    "info",
                    "health",
                )
                output = self.command(host, args, mutate=not readonly)
            rows = json.loads(self.command(host, ["list", "--json"]))
            if not isinstance(rows, list):
                raise ValueError("Invalid host inventory response")
            with self.lock:
                self.inventory[ident] = rows
                self.jobs[ident] = {
                    "state": "done",
                    "message": f"{action}: complete",
                    "output": output[-60000:],
                }
        except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
            with self.lock:
                self.jobs[ident] = {"state": "error", "message": str(exc), "output": output[-60000:]}
