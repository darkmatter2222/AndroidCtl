import errno
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import Mock, patch

from androidctl.web import Workbench, bind_server, make_handler
from http.server import ThreadingHTTPServer


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workbench = Workbench(state=Path(self.tmp.name) / "devices.json")

    def test_saved_inventory_and_persistence(self):
        self.workbench.action({"action": "save", "serial": "host:5555", "name": "Lab"})
        with patch.object(
            self.workbench,
            "run",
            return_value="List of devices attached\nhost:5555 device model:Pixel\nusb offline\n",
        ):
            rows = self.workbench.devices()
        self.assertEqual(rows[0]["name"], "Lab")
        self.assertEqual(rows[0]["state"], "device")
        self.assertEqual(rows[1]["state"], "offline")
        self.assertEqual(Workbench(state=self.workbench.state).saved, {"host:5555": "Lab"})

    def test_reject_unsafe_input(self):
        for serial in ["-a", "host;id", "$(id)", "", None]:
            with self.assertRaises(ValueError):
                self.workbench.serial(serial)
        with patch.object(self.workbench, "devices", return_value=[{"serial": "usb", "state": "device"}]):
            for data in [
                {"action": "key", "key": "3;id"},
                {"action": "tap", "points": [-1, 4]},
                {"action": "shell"},
            ]:
                with self.assertRaises(ValueError):
                    self.workbench.action({"serial": "usb", **data})

    def test_explicit_serial_and_coordinates(self):
        with (
            patch.object(self.workbench, "devices", return_value=[{"serial": "usb", "state": "device"}]),
            patch.object(self.workbench, "run") as run,
        ):
            self.workbench.action({"serial": "usb", "action": "swipe", "points": [10, 20, 30, 40]})
            run.assert_called_once_with("-s", "usb", "shell", "input", "swipe", "10", "20", "30", "40", "300")

    def test_http_boundary(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.workbench, "test-token"))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        def request(path, headers=None, method="GET", body=None):
            conn = HTTPConnection("127.0.0.1", server.server_port)
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            status, data = response.status, response.read()
            conn.close()
            return status, data

        self.assertEqual(request("/")[0], 200)
        self.assertEqual(request("/api/devices")[0], 401)
        self.assertEqual(request("/", {"Host": "evil.test"})[0], 403)
        headers = {"X-AndroidCtl-Token": "test-token", "Origin": "https://evil.test"}
        self.assertEqual(request("/api/action", headers, "POST", "{}")[0], 403)
        headers.pop("Origin")
        self.assertEqual(request("/api/action", headers, "POST", "[]")[0], 400)
        body = json.dumps({"action": "save", "serial": "host:5555", "name": "Lab"})
        self.assertEqual(request("/api/action", headers, "POST", body)[0], 200)
        with patch.object(self.workbench, "run", return_value="List of devices attached\n"):
            status, data = request("/api/devices", headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)["devices"][0]["state"], "disconnected")


class BindTests(unittest.TestCase):
    def test_default_falls_back_for_blocked_or_busy_port(self):
        for code in (errno.EACCES, errno.EADDRINUSE):
            server = Mock()
            with patch(
                "androidctl.web.ThreadingHTTPServer", side_effect=[OSError(code, "blocked"), server]
            ) as factory:
                self.assertIs(bind_server("handler"), server)
                self.assertEqual(factory.call_args_list[0].args, (("127.0.0.1", 8765), "handler"))
                self.assertEqual(factory.call_args_list[1].args, (("127.0.0.1", 0), "handler"))

    def test_explicit_port_and_unrelated_errors_do_not_fallback(self):
        for port, code in ((8765, errno.EACCES), (0, errno.EACCES), (None, errno.EBADF)):
            with patch("androidctl.web.ThreadingHTTPServer", side_effect=OSError(code, "failed")) as factory:
                with self.assertRaises(OSError):
                    bind_server("handler", port)
                factory.assert_called_once()

    def test_real_automatic_port(self):
        server = bind_server(make_handler(None, "token"), 0)
        try:
            self.assertGreater(server.server_port, 0)
            self.assertEqual(server.server_address[0], "127.0.0.1")
        finally:
            server.server_close()
