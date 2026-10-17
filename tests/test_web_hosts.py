import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from androidctl.web_hosts import Hosts
from androidctl import gpu
from androidctl.errors import Error


class HostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.hosts = Hosts(Path(self.temp.name) / "hosts.json")
        self.hosts.save({"id": "lab", "target": "user@lab", "endpoint_host": "lab"})
        self.hosts.inventory["lab"] = [{"id": "01"}]

    def test_reject_ssh_and_profile_injection(self):
        for target in ("-oProxyCommand=bad", "user@host;id", "user@host bad"):
            with self.assertRaises(ValueError):
                self.hosts.save({"id": "lab", "target": target, "endpoint_host": "lab"})
        with self.assertRaises(ValueError):
            self.hosts.action({"host": "lab", "action": "create", "instance": "02", "profile": "pixel;id"})

    def test_exact_delete_confirmation_and_preserve_flag(self):
        with self.assertRaises(ValueError):
            self.hosts.action(
                {
                    "host": "lab",
                    "action": "delete",
                    "instance": "01",
                    "confirm": "DELETE 02",
                    "erase_data": True,
                }
            )
        with patch("androidctl.web_hosts.threading.Thread") as thread:
            self.hosts.action(
                {
                    "host": "lab",
                    "action": "delete",
                    "instance": "01",
                    "confirm": "DELETE 01",
                    "erase_data": False,
                }
            )
        self.assertEqual(thread.call_args.kwargs["args"][-1], ["delete", "01", "--yes", "--keep-data"])

    def test_busy_host_rejected(self):
        self.hosts.jobs["lab"] = {"state": "running"}
        with self.assertRaises(ValueError):
            self.hosts.action({"host": "lab", "action": "stop", "instance": "01"})

    def test_ssh_command_no_interactive_or_shell(self):
        with patch(
            "androidctl.web_hosts.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="OK", stderr=""),
        ) as run:
            self.hosts.command(self.hosts.profiles["lab"], ["start", "01"], mutate=True)
        argv = run.call_args.args[0]
        self.assertIn("BatchMode=yes", argv)
        self.assertIn("StrictHostKeyChecking=yes", argv)
        self.assertEqual(argv[-1], "sudo -n androidctl start 01")
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_scan_stopped_instances_and_command_errors(self):
        with patch.object(self.hosts, "command", return_value=json.dumps([{"id": "01", "state": "stopped"}])):
            self.hosts.worker("lab", self.hosts.profiles["lab"], "scan", [])
        self.assertEqual(self.hosts.snapshot()[0]["instances"][0]["state"], "stopped")
        with patch.object(self.hosts, "command", side_effect=ValueError("sudo password required")):
            self.hosts.worker("lab", self.hosts.profiles["lab"], "start", ["start", "01"])
        self.assertEqual(self.hosts.jobs["lab"]["state"], "error")
        self.assertIn("sudo", self.hosts.jobs["lab"]["message"])

    def test_renderer_allowlist(self):
        with self.assertRaises(ValueError):
            self.hosts.action({"host": "lab", "action": "renderer", "instance": "01", "gpu": "host;id"})
        with patch("androidctl.web_hosts.threading.Thread") as thread:
            self.hosts.action({"host": "lab", "action": "renderer", "instance": "01", "gpu": "host"})
        self.assertEqual(thread.call_args.kwargs["args"][-1], ["renderer", "01", "--gpu", "host"])


class NvidiaTests(unittest.TestCase):
    def setUp(self):
        self.device = {"pci": "0000:01:00.0", "driver": "nvidia", "render_node": "", "nodes": []}
        self.instance = SimpleNamespace(gpu_mode="host", gpu_pci="0000:01:00.0", dri_prime="auto")

    def test_selected_nvidia_device_and_shared_nodes_only(self):
        with (
            patch.object(gpu, "discover", return_value=[self.device]),
            patch.object(Path, "read_text", return_value="Device Minor: 0\n"),
            patch.object(Path, "exists", return_value=True),
        ):
            selected = gpu.selection(self.instance)
        self.assertIn("/dev/nvidia0", selected["nodes"])
        self.assertIn("/dev/nvidiactl", selected["nodes"])
        self.assertNotIn("/dev/nvidia1", selected["nodes"])

    def test_multi_nvidia_fails_closed(self):
        with patch.object(
            gpu, "discover", return_value=[self.device, {**self.device, "pci": "0000:02:00.0"}]
        ):
            with self.assertRaises(Error):
                gpu.selection(self.instance)

    def test_nvidia_environment_never_forces_software(self):
        with (
            patch.object(gpu, "selection", return_value=self.device),
            patch.object(Path, "exists", return_value=True),
        ):
            env = gpu.environment(self.instance)
        self.assertEqual(env["__GLX_VENDOR_LIBRARY_NAME"], "nvidia")
        self.assertNotIn("LIBGL_ALWAYS_SOFTWARE", env)

    def test_running_renderer_change_rejected(self):
        with (
            patch("androidctl.util.lock") as lock,
            patch("androidctl.systemd.properties", return_value={"ActiveState": "active"}),
        ):
            lock.return_value.__exit__.return_value = False
            with self.assertRaises(Error):
                gpu.configure(SimpleNamespace(), SimpleNamespace(id="01"), "host")
