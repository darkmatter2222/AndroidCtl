import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from androidctl.web import Workbench, make_handler
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
