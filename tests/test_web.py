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


class DisplayTests(WebTests):
    def test_profiles_match_native_and_override(self):
        with patch.object(
            self.workbench,
            "run",
            side_effect=[
                "Physical size: 1344x2992\nOverride size: 672x1496",
                "Physical density: 480\nOverride density: 240",
            ],
        ):
            result = self.workbench.display("usb")
        profiles = {p["id"]: p for p in result["profiles"]}
        self.assertEqual(profiles["current"]["size"], "672x1496")
        self.assertEqual(profiles["current"]["density"], 240)
        self.assertEqual(profiles["default"]["size"], "reset")
        self.assertEqual(profiles["50"]["size"], "672x1496")
        self.assertEqual(profiles["50"]["density"], 240)
        self.assertEqual(profiles["25"]["size"], "336x748")

    def test_disconnect_retains_unsaved_device_and_blocks_frames(self):
        with patch.object(self.workbench, "run", return_value="disconnected") as run:
            self.workbench.action({"serial": "host:5555", "action": "disconnect"})
            run.assert_called_once_with("disconnect", "host:5555")
        self.assertIn("host:5555", self.workbench.saved)
        with patch.object(self.workbench, "run", return_value="List of devices attached\nhost:5555 device\n"):
            self.assertEqual(self.workbench.devices()[0]["state"], "disconnected")
        with patch.object(self.workbench, "run") as run:
            with self.assertRaises(ValueError):
                self.workbench.frame("host:5555")
            run.assert_not_called()
        with patch.object(self.workbench, "run", return_value="connected"):
            self.workbench.action({"serial": "host:5555", "action": "connect"})
        self.assertNotIn("host:5555", self.workbench.detached)

    def test_usb_detach_does_not_disconnect_other_transports(self):
        with patch.object(self.workbench, "run") as run:
            self.workbench.action({"serial": "usb", "action": "disconnect"})
            run.assert_not_called()
            self.workbench.action({"serial": "usb", "action": "connect"})
            run.assert_not_called()
        self.assertNotIn("usb", self.workbench.detached)

    def test_restart_waits_for_new_boot_then_applies(self):
        profile = {"id": "50", "size": "672x1496", "density": 240}
        with (
            patch.object(self.workbench, "run", side_effect=["", "old", "1", "new", "1"]) as run,
            patch.object(self.workbench, "apply_display") as apply,
            patch("androidctl.web.time.sleep"),
        ):
            self.workbench.restart_worker("usb", profile, "old")
        self.assertEqual(run.call_args_list[0].args, ("-s", "usb", "reboot"))
        apply.assert_called_once_with("usb", profile)
        self.assertEqual(self.workbench.jobs["usb"]["state"], "done")

    def test_restart_failure_is_reported(self):
        with patch.object(self.workbench, "run", side_effect=ValueError("reboot denied")):
            self.workbench.restart_worker("usb", {}, "old")
        self.assertEqual(self.workbench.jobs["usb"]["state"], "error")
        self.assertIn("reboot denied", self.workbench.jobs["usb"]["message"])

    def test_unknown_profile_never_reboots(self):
        with (
            patch.object(self.workbench, "devices", return_value=[{"serial": "usb", "state": "device"}]),
            patch.object(self.workbench, "display", return_value={"profiles": []}),
            patch.object(self.workbench, "run") as run,
        ):
            with self.assertRaises(ValueError):
                self.workbench.action({"serial": "usb", "action": "restart", "profile": ";reboot"})
            run.assert_not_called()

    def test_reset_is_verified(self):
        profile = {"id": "default", "size": "reset", "density": "reset"}
        actual = {
            "profiles": [{"size": "1344x2992", "density": 480}, profile],
            "size": "Physical size: 1344x2992",
            "density": "Physical density: 480",
        }
        with (
            patch.object(self.workbench, "run") as run,
            patch.object(self.workbench, "display", return_value=actual),
        ):
            self.workbench.apply_display("usb", profile)
        self.assertEqual(run.call_args_list[0].args, ("-s", "usb", "shell", "wm", "size", "reset"))
        self.assertEqual(run.call_args_list[1].args, ("-s", "usb", "shell", "wm", "density", "reset"))
