"""Local ADB workbench. Intentionally independent of Linux host-manager imports."""

import argparse
import errno
import json
import ipaddress
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .web_hosts import Hosts


class Workbench:
    def __init__(self, adb="adb", scrcpy="scrcpy", port=5037, state=None):
        self.adb = adb
        self.scrcpy = scrcpy
        self.port = port
        self.state = Path(state or Path.home() / ".androidctl" / "web-devices.json")
        self.hosts = Hosts(self.state.with_name("web-hosts.json"))
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(8)
        self.capture_slots = threading.BoundedSemaphore(2)
        self.viewers = {}
        self.detached = set()
        self.jobs = {}
        self.device_locks = {}
        self.saved = json.loads(self.state.read_text()) if self.state.exists() else {}

    def run(self, *args, binary=False):
        with self.slots:
            result = subprocess.run([self.adb, "-P", str(self.port), *args], capture_output=True, timeout=15)
        if result.returncode:
            raise ValueError(result.stderr.decode(errors="replace").strip() or "ADB command failed")
        return result.stdout if binary else result.stdout.decode(errors="replace").strip()

    @staticmethod
    def serial(value):
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:\[\]-]{1,200}", value):
            raise ValueError("Invalid device serial")
        if value.startswith("-"):
            raise ValueError("Invalid device serial")
        return value

    def devices(self):
        with self.lock:
            rows = {s: {"serial": s, "name": n, "state": "disconnected"} for s, n in self.saved.items()}
        for host in self.hosts.snapshot():
            for instance in host["instances"]:
                serial = f"{host['endpoint_host']}:{instance['remote_adb_port']}"
                row = rows.setdefault(
                    serial, {"serial": serial, "name": instance["name"], "state": "disconnected"}
                )
                row["managed"] = {
                    "host": host["id"],
                    "id": instance["id"],
                    "state": instance["state"],
                    "gpu": instance["gpu_mode"],
                    "ram": instance["ram_mb"],
                    "cpus": instance["cpu_cores"],
                    "display_scale": instance.get("display_scale", 0),
                    "autostart": instance.get("autostart", False),
                }
                if instance["state"] in ("stopped", "failed"):
                    row["state"] = instance["state"]
        try:
            transports = self.run("devices", "-l")
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            if not rows:
                raise ValueError(f"ADB unavailable: {exc}") from exc
            transports = ""
            for row in rows.values():
                row["details"] = f"ADB unavailable: {exc}"
        for line in transports.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, status = parts[:2]
            row = rows.setdefault(serial, {"serial": serial, "name": serial})
            row.update(state=status, details=" ".join(parts[2:]))
        with self.lock:
            for serial, row in rows.items():
                if serial in self.detached:
                    row["state"] = "disconnected"
                job = self.jobs.get(serial)
                if job:
                    row["operation"] = dict(job)
                    if job["state"] == "running":
                        row["state"] = "restarting"
        return list(rows.values())

    def save(self):
        self.state.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.saved, indent=2))
        os.replace(tmp, self.state)

    def device_lock(self, serial):
        with self.lock:
            return self.device_locks.setdefault(serial, threading.RLock())

    def display(self, serial):
        size = self.run("-s", serial, "shell", "wm", "size")
        density = self.run("-s", serial, "shell", "wm", "density")
        physical = re.search(r"Physical size:\s*(\d+)x(\d+)", size)
        dpi = re.search(r"Physical density:\s*(\d+)", density)
        override = re.search(r"Override size:\s*(\d+)x(\d+)", size)
        override_dpi = re.search(r"Override density:\s*(\d+)", density)
        if not physical or not dpi:
            raise ValueError("Cannot read native display size/density")
        width, height = map(int, physical.groups())
        native_dpi = int(dpi[1])
        current = override or physical
        profiles = [
            {
                "id": "current",
                "label": f"Keep current — {current[1]}×{current[2]}",
                "size": f"{current[1]}x{current[2]}",
                "density": int((override_dpi or dpi)[1]),
            },
            {
                "id": "default",
                "label": f"Native default — {width}×{height}",
                "size": "reset",
                "density": "reset",
            },
        ]
        for percent in (75, 50, 33, 25):
            w, h = max(2, round(width * percent / 200) * 2), max(2, round(height * percent / 200) * 2)
            scaled_dpi = max(72, round(native_dpi * percent / 100))
            profiles.append(
                {
                    "id": str(percent),
                    "label": f"{w}×{h} — {percent}% / {scaled_dpi} dpi",
                    "size": f"{w}x{h}",
                    "density": scaled_dpi,
                }
            )
        return {"profiles": profiles, "size": size, "density": density}

    def apply_display(self, serial, profile):
        self.run("-s", serial, "shell", "wm", "size", profile["size"])
        self.run("-s", serial, "shell", "wm", "density", str(profile["density"]))
        actual = self.display(serial)
        current = actual["profiles"][0]
        expected = actual["profiles"][1] if profile["id"] == "default" else profile
        if expected["size"] == "reset":
            if "Override" in actual["size"] or "Override" in actual["density"]:
                raise ValueError("Android did not clear the display override")
        elif current["size"] != expected["size"] or current["density"] != expected["density"]:
            raise ValueError("Android did not apply the requested size/density")
        return actual

    def restart_worker(self, serial, profile, old_boot):
        try:
            self.run("-s", serial, "reboot")
            deadline = time.monotonic() + 240
            last_error = "Device has not completed a new boot"
            while time.monotonic() < deadline:
                try:
                    if ":" in serial:
                        self.run("connect", serial)
                    boot = self.run("-s", serial, "shell", "cat", "/proc/sys/kernel/random/boot_id")
                    ready = self.run("-s", serial, "shell", "getprop", "sys.boot_completed")
                    if boot and boot != old_boot and ready == "1":
                        self.apply_display(serial, profile)
                        with self.lock:
                            self.jobs[serial] = {"state": "done", "message": "Restarted; display verified"}
                        return
                except (OSError, ValueError, subprocess.SubprocessError) as exc:
                    last_error = str(exc)
                time.sleep(2)
            raise ValueError(
                f"Restart timed out after 240 seconds: {last_error}; reconnect and inspect the device"
            )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            with self.lock:
                self.jobs[serial] = {"state": "error", "message": str(exc)}

    def frame(self, serial):
        with self.lock:
            if serial in self.detached or self.jobs.get(serial, {}).get("state") == "running":
                raise ValueError("Device disconnected or restarting; preview stopped")
        # Do not queue an unbounded screenshot backlog ahead of control commands.
        if not self.capture_slots.acquire(blocking=False):
            raise ValueError("Capture capacity busy; next preview will retry")
        try:
            return self.run("-s", serial, "exec-out", "screencap", "-p", binary=True)
        finally:
            self.capture_slots.release()

    def action(self, data):
        action = data.get("action")
        serial = self.serial(data.get("serial"))
        with self.lock:
            if self.jobs.get(serial, {}).get("state") == "running":
                raise ValueError("Restart already in progress; wait for completion")
        if action == "disconnect":
            with self.lock:
                self.saved.setdefault(serial, serial)
                self.save()
                self.detached.add(serial)
                process = self.viewers.get(serial)
                if process and process.poll() is None:
                    process.terminate()
            # ADB cannot detach one USB transport. Pause its workbench access only.
            if ":" in serial:
                self.run("disconnect", serial)
            return {"message": "Disconnected from workbench; previews stopped. Android is still running."}
        if action in {"save", "connect", "pair"}:
            try:
                ipaddress.ip_address(serial.strip("[]"))
            except ValueError:
                pass
            else:
                raise ValueError(
                    "Network devices need an IP address AND port, e.g. "
                    "192.168.86.48:15551. The name field is only a display label."
                )
        if action == "connect" and ":" not in serial:
            if self.run("-s", serial, "get-state").strip() != "device":
                raise ValueError("Device is not online/authorized; check its connection and USB authorization")
            with self.lock:
                self.detached.discard(serial)
            return {"message": "Workbench reattached; device is online"}
        if action == "save":
            name = str(data.get("name", serial))[:100]
            with self.lock:
                self.saved[serial] = name
                self.save()
            return {"message": "Saved connection"}
        if action == "forget":
            with self.lock:
                self.saved.pop(serial, None)
                self.save()
            return {"message": "Removed saved connection; device was not disconnected"}
        if action in ("connect", "pair"):
            if not re.fullmatch(r"(?:[A-Za-z0-9_.-]+|\[[0-9a-fA-F:]+\]):[0-9]{1,5}", serial):
                raise ValueError("Network connection requires host:port")
            if not 1 <= int(serial.rsplit(":", 1)[1]) <= 65535:
                raise ValueError("Invalid port")
            args = [action, serial]
            if action == "pair":
                code = str(data.get("code", ""))
                if not re.fullmatch(r"\d{6}", code):
                    raise ValueError("Pairing code must contain six digits")
                args.append(code)
            message = self.run(*args)
            if any(word in message.lower() for word in ("failed", "cannot", "unable")):
                raise ValueError(message)
            if action == "connect":
                with self.lock:
                    self.detached.discard(serial)
            return {"message": message}
        if not any(d["serial"] == serial and d["state"] == "device" for d in self.devices()):
            raise ValueError("Device is not online/authorized")
        if action == "display":
            return self.display(serial)
        if action in ("resolution", "restart"):
            with self.device_lock(serial):
                if self.jobs.get(serial, {}).get("state") == "running":
                    raise ValueError("Restart already in progress")
                profiles = self.display(serial)["profiles"]
                profile = next((p for p in profiles if p["id"] == data.get("profile", "current")), None)
                if profile is None:
                    raise ValueError("Unknown resolution profile")
                if action == "resolution":
                    result = self.apply_display(serial, profile)
                    return {"message": "Resolution applied and verified", **result}
                old_boot = self.run("-s", serial, "shell", "cat", "/proc/sys/kernel/random/boot_id")
                if not old_boot:
                    raise ValueError("Cannot read boot identity; restart not issued")
                self.saved.setdefault(serial, serial)
                self.save()
                self.jobs[serial] = {
                    "state": "running",
                    "message": "Restarting Android; waiting for boot and display",
                }
                threading.Thread(
                    target=self.restart_worker, args=(serial, profile, old_boot), daemon=True
                ).start()
            return {"message": "Restart requested; keep the workbench server running"}
        if action == "info":
            return {
                "properties": self.run("-s", serial, "shell", "getprop"),
                "battery": self.run("-s", serial, "shell", "dumpsys", "battery"),
                "display": self.run("-s", serial, "shell", "wm", "size"),
            }
        if action == "scrcpy":
            with self.lock:
                process = self.viewers.get(serial)
                if process and process.poll() is None:
                    return {"message": "scrcpy already running"}
                env = dict(os.environ, ADB=self.adb, ANDROID_ADB_SERVER_PORT=str(self.port))
                process = subprocess.Popen([self.scrcpy, "-s", serial, "--no-audio", "--max-fps=30"], env=env)
                self.viewers[serial] = process
            return {"message": "scrcpy launched on the server desktop", "pid": process.pid}
        if action == "key":
            key = data.get("key")
            if key not in (3, 4, 24, 25, 26, 82, 187):
                raise ValueError("Unsupported key")
            self.run("-s", serial, "shell", "input", "keyevent", str(key))
        elif action in ("tap", "swipe"):
            points = data.get("points")
            if not isinstance(points, list) or len(points) != (2 if action == "tap" else 4):
                raise ValueError("Invalid coordinates")
            if any(type(v) is not int or not 0 <= v <= 16384 for v in points):
                raise ValueError("Invalid coordinates")
            args = [str(v) for v in points]
            if action == "swipe":
                args.append("300")
            self.run("-s", serial, "shell", "input", action, *args)
        else:
            raise ValueError("Unknown action")
        return {"message": "OK"}


def make_handler(workbench, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never log pairing codes or access tokens.

        def respond(self, status, body, mime="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; frame-ancestors 'none'"
            )
            self.end_headers()
            self.wfile.write(body)

        def allowed(self):
            host = self.headers.get("Host", "")
            expected = f"127.0.0.1:{self.server.server_port}"
            origin = self.headers.get("Origin")
            return host == expected and (origin is None or origin == f"http://{expected}")

        def do_GET(self):
            if not self.allowed():
                return self.respond(403, {"error": "Invalid host/origin"})
            url = urlsplit(self.path)
            assets = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
            if url.path in assets:
                name = assets[url.path]
                mime = {"html": "text/html; charset=utf-8", "js": "text/javascript", "css": "text/css"}
                return self.respond(
                    200,
                    (Path(__file__).parent / "web_assets" / name).read_bytes(),
                    mime[name.rsplit(".", 1)[1]],
                )
            if not secrets.compare_digest(self.headers.get("X-AndroidCtl-Token", ""), token):
                return self.respond(401, {"error": "Missing/invalid session token"})
            try:
                if url.path == "/api/hosts":
                    return self.respond(200, {"hosts": workbench.hosts.snapshot()})
                if url.path == "/api/devices":
                    return self.respond(200, {"devices": workbench.devices()})
                if url.path == "/api/frame":
                    serial = workbench.serial(parse_qs(url.query).get("serial", [None])[0])
                    frame = workbench.frame(serial)
                    if not frame.startswith(b"\x89PNG\r\n\x1a\n"):
                        raise ValueError("Device did not return a PNG frame")
                    return self.respond(200, frame, "image/png")
                self.respond(404, {"error": "Not found"})
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                self.respond(400, {"error": str(exc)})

        def do_POST(self):
            if not self.allowed() or not secrets.compare_digest(
                self.headers.get("X-AndroidCtl-Token", ""), token
            ):
                return self.respond(403, {"error": "Invalid host/origin/token"})
            if self.path not in ("/api/action", "/api/host-action"):
                return self.respond(404, {"error": "Not found"})
            try:
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 4096:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("Expected JSON object")
                self.respond(
                    200,
                    workbench.hosts.action(data)
                    if self.path == "/api/host-action"
                    else workbench.action(data),
                )
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                self.respond(400, {"error": str(exc)})

    return Handler


def bind_server(handler, port=None):
    """Prefer 8765, allowing the OS to choose only when no port was specified."""
    requested = 8765 if port is None else port
    try:
        return ThreadingHTTPServer(("127.0.0.1", requested), handler)
    except OSError as exc:
        if port is not None or not (
            exc.errno in (errno.EACCES, errno.EADDRINUSE) or getattr(exc, "winerror", None) in (10013, 10048)
        ):
            raise
        print("Default port 8765 is unavailable; choosing an available local port.", file=sys.stderr)
        return ThreadingHTTPServer(("127.0.0.1", 0), handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Start the local AndroidCtl device workbench")
    parser.add_argument(
        "--port", type=int, help="Local port (default: 8765 with automatic fallback; 0: auto)"
    )
    parser.add_argument("--adb", default=shutil.which("adb") or "adb")
    parser.add_argument("--scrcpy", default=shutil.which("scrcpy") or "scrcpy")
    parser.add_argument("--adb-port", type=int, default=5037)
    parser.add_argument("--state")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    if args.port is not None and not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    token = secrets.token_urlsafe(32)
    workbench = Workbench(args.adb, args.scrcpy, args.adb_port, args.state)
    try:
        server = bind_server(make_handler(workbench, token), args.port)
    except OSError as exc:
        print(
            f"Cannot start the local web listener: {exc}\n"
            "Try start-web.bat --port 0 (or androidctl-web --port 0). "
            "If automatic selection also fails, check local security software policy.",
            file=sys.stderr,
        )
        return 1
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}/#token={token}"
    print(f"AndroidCtl workbench: {url}", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
