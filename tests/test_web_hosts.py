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

    def test_create_and_display_scale_commands(self):
        for action, ident, flag in (("create", "02", "--display-scale"), ("display", "01", "--scale")):
            self.hosts.jobs.clear()
            with patch("androidctl.web_hosts.threading.Thread") as thread:
                self.hosts.action({"host": "lab", "action": action, "instance": ident, "display_scale": 50})
            command = thread.call_args.kwargs["args"][-1]
            self.assertEqual(command[command.index(flag) + 1], "50")
        self.hosts.jobs.clear()
        with self.assertRaises(ValueError):
            self.hosts.action(
                {"host": "lab", "action": "display", "instance": "01", "display_scale": "50;id"}
            )

    def test_reports_do_not_use_sudo(self):
        with patch.object(self.hosts, "command", side_effect=["report", "[]"]) as command:
            self.hosts.worker("lab", self.hosts.profiles["lab"], "logs", ["logs", "01", "--since", "30m"])
        self.assertFalse(command.call_args_list[0].kwargs["mutate"])

    def test_lifecycle_additions_and_unknown_commands(self):
        for action in ("restart", "enable", "disable"):
            self.hosts.jobs.clear()
            with patch("androidctl.web_hosts.threading.Thread") as thread:
                self.hosts.action({"host": "lab", "action": action, "instance": "01"})
            self.assertEqual(thread.call_args.kwargs["args"][-1], [action, "01"])
        self.hosts.jobs.clear()
        with self.assertRaises(ValueError):
            self.hosts.action({"host": "lab", "action": "shell", "instance": "01"})

    def test_inventory_survives_restart_and_failed_refresh(self):
        rows = [{"id": "01", "name": "phone", "state": "stopped"}]
        with patch.object(self.hosts, "command", return_value=json.dumps(rows)):
            self.hosts.worker("lab", self.hosts.profiles["lab"], "scan", [])
        restored = Hosts(self.hosts.state)
        self.assertEqual(restored.snapshot()[0]["instances"], rows)
        with patch.object(restored, "command", side_effect=ValueError("Permission denied (publickey)")):
            restored.worker("lab", restored.profiles["lab"], "scan", [])
        view = restored.snapshot()[0]
        self.assertEqual(view["instances"], rows)
        self.assertTrue(view["inventory_known"])
        self.assertTrue(view["inventory_stale"])

    def test_first_load_scans_once_without_creating_anything(self):
        with patch("androidctl.web_hosts.threading.Thread") as thread:
            self.hosts.snapshot(auto_scan=True)
            self.hosts.snapshot(auto_scan=True)
        self.assertEqual(thread.call_count, 1)
        self.assertEqual(thread.call_args.kwargs["args"][2], "scan")

    def test_old_server_inventory_fallback_is_specific(self):
        with patch.object(
            self.hosts,
            "command",
            side_effect=[ValueError("invalid choice: 'inventory'"), '[{"id":"01","state":"stopped"}]'],
        ) as command:
            self.hosts.worker("lab", self.hosts.profiles["lab"], "scan", [])
        self.assertEqual(command.call_args_list[0].args[1], ["inventory", "--json"])
        self.assertEqual(command.call_args_list[1].args[1], ["list", "--json"])
        self.assertEqual(self.hosts.jobs["lab"]["state"], "done")
        with patch.object(self.hosts, "command", side_effect=ValueError("Permission denied")) as command:
            self.hosts.worker("lab", self.hosts.profiles["lab"], "scan", [])
        self.assertEqual(command.call_count, 1)

    def test_invalid_inventory_does_not_erase_previous_rows(self):
        rows = list(self.hosts.inventory["lab"])
        with patch.object(self.hosts, "command", return_value="login banner, not JSON"):
            self.hosts.worker("lab", self.hosts.profiles["lab"], "scan", [])
        self.assertEqual(self.hosts.inventory["lab"], rows)
        self.assertIn("invalid JSON", self.hosts.jobs["lab"]["message"])

    def test_catalog_create_supports_large_id_and_runtime_ports(self):
        with patch("androidctl.web_hosts.threading.Thread") as thread:
            self.hosts.action(
                {
                    "host": "lab",
                    "action": "create",
                    "instance": "200",
                    "runtime_ports": True,
                    "disk": "16G",
                    "image": "google_apis",
                }
            )
        args = thread.call_args.kwargs["args"][-1]
        self.assertEqual(args[:2], ["create", "200"])
        self.assertIn("--runtime-ports", args)
        self.assertIn("--disk", args)

    def test_capacity_only_sets_bounded_admission_limit(self):
        with patch("androidctl.web_hosts.threading.Thread") as thread:
            self.hosts.action({"host": "lab", "action": "capacity", "maximum": 3})
        self.assertEqual(thread.call_args.kwargs["args"][-1], ["config", "set", "max_running_instances", "3"])
        self.hosts.jobs.clear()
        with self.assertRaises(ValueError):
            self.hosts.action({"host": "lab", "action": "capacity", "maximum": 0})


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
