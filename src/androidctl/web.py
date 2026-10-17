"""Local ADB workbench. Intentionally independent of Linux host-manager imports."""

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


class Workbench:
    def __init__(self, adb="adb", scrcpy="scrcpy", port=5037, state=None):
        self.adb = adb
        self.scrcpy = scrcpy
        self.port = port
        self.state = Path(state or Path.home() / ".androidctl" / "web-devices.json")
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(8)
        self.viewers = {}
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
        for line in self.run("devices", "-l").splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, status = parts[:2]
            row = rows.setdefault(serial, {"serial": serial, "name": serial})
            row.update(state=status, details=" ".join(parts[2:]))
        return list(rows.values())

    def save(self):
        self.state.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.saved, indent=2))
        os.replace(tmp, self.state)

    def action(self, data):
        action = data.get("action")
        serial = self.serial(data.get("serial"))
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
        if action in ("connect", "disconnect", "pair"):
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
            return {"message": message}
        if not any(d["serial"] == serial and d["state"] == "device" for d in self.devices()):
            raise ValueError("Device is not online/authorized")
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
                if url.path == "/api/devices":
                    return self.respond(200, {"devices": workbench.devices()})
                if url.path == "/api/frame":
                    serial = workbench.serial(parse_qs(url.query).get("serial", [None])[0])
                    frame = workbench.run("-s", serial, "exec-out", "screencap", "-p", binary=True)
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
            if self.path != "/api/action":
                return self.respond(404, {"error": "Not found"})
            try:
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 4096:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("Expected JSON object")
                self.respond(200, workbench.action(data))
            except (ValueError, OSError, subprocess.SubprocessError) as exc:
                self.respond(400, {"error": str(exc)})

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description="Start the local AndroidCtl device workbench")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--adb", default=shutil.which("adb") or "adb")
    parser.add_argument("--scrcpy", default=shutil.which("scrcpy") or "scrcpy")
    parser.add_argument("--adb-port", type=int, default=5037)
    parser.add_argument("--state")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    token = secrets.token_urlsafe(32)
    workbench = Workbench(args.adb, args.scrcpy, args.adb_port, args.state)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(workbench, token))
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
