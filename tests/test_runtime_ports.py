"""Catalog identities outlive emulator runtime slots."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from androidctl import ports, service
from androidctl.config import Config, Instance, get_instance, save
from androidctl.errors import Error


def reserved(n):
    return Instance(
        f"{n:02d}", f"Phone_{n}", 35, "pixel_8_pro", "google_apis", 5554, 5555, 15550 + n, runtime_ports=True
    )


class RuntimePortsTests(unittest.TestCase):
    def test_two_hundred_saved_identities_have_unique_public_endpoints(self):
        catalog = [reserved(n) for n in range(1, 201)]
        for device in catalog:
            ports.conflicts(device, catalog, 5038)
        self.assertEqual(len({i.remote_adb_port for i in catalog}), 200)
        with patch("androidctl.ports.available"):
            allocations = {}
            for obj in catalog[:3]:
                console, local = ports.runtime_pair(obj, catalog, 5038, allocations)
                self.assertEqual(local, console + 1)
                allocations[obj.id] = {"console_port": console}
            self.assertEqual(len({v["console_port"] for v in allocations.values()}), 3)
            old = allocations.pop("01")["console_port"]
            self.assertEqual(ports.runtime_pair(catalog[-1], catalog, 5038, allocations)[0], old)
        self.assertEqual(catalog[-1].remote_adb_port, 15750)

    def test_fixed_legacy_pairs_and_foreign_listeners_are_not_reused(self):
        obj = reserved(200)
        legacy = replace(reserved(1), runtime_ports=False)
        with patch("androidctl.ports.available", side_effect=[Error("occupied"), None]):
            console, _ = ports.runtime_pair(obj, [legacy, obj], 5038, {})
        self.assertEqual(console, 5558)
        with self.assertRaises(Error):
            ports.conflicts(obj, [replace(legacy, remote_adb_port=obj.remote_adb_port)], 5038)

    def test_exhausted_runtime_pool_fails_without_reassigning_public_port(self):
        obj = reserved(200)
        allocations = {str(i): {"console_port": c} for i, c in enumerate(range(5554, 5683, 2))}
        with self.assertRaises(Error):
            ports.runtime_pair(obj, [obj], 5038, allocations)
        self.assertEqual(obj.remote_adb_port, 15750)

    def test_preflight_handoff_launch_proxy_and_release_preserve_storage(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = Config(
                instance_root=root + "/instances",
                avd_root=root + "/avd",
                runtime_root=root + "/run",
                max_running_instances=3,
            )
            obj = reserved(200)
            legacy = replace(reserved(1), runtime_ports=False)
            for i in (legacy, obj):
                save(Path(cfg.instance_root) / f"{i.id}.conf", i, "instance")
            data = Path(cfg.avd_root) / (obj.name + ".avd")
            data.mkdir(parents=True)
            (data / "config.ini").write_text("hw.lcd.width=1344")
            (data / "userdata.img").write_bytes(b"preserve this disk")
            (Path(cfg.avd_root) / (obj.name + ".ini")).touch()
            with (
                patch("androidctl.service.require_root"),
                patch("androidctl.service.host") as host,
                patch("androidctl.service.SDK.installed", return_value=True),
                patch("androidctl.service.gpu.selection"),
                patch("androidctl.service.systemd.properties", return_value={"ActiveState": "inactive"}),
                patch("androidctl.ports.available"),
            ):
                host.available_ram.return_value = 64000
                host.bind_address.return_value = "127.0.0.1"
                service.preflight(cfg, obj)
            active = get_instance(cfg, "200")
            self.assertEqual(active.console_port, 5556)
            self.assertEqual(active.local_adb_port, 5557)
            self.assertEqual(active.remote_adb_port, 15750)
            with (
                patch("androidctl.service.os.execve") as launch,
                patch("androidctl.service.os.geteuid", return_value=999),
                patch("androidctl.service.SDK") as sdk,
            ):
                sdk.return_value.tool.return_value = "/emulator"
                service.launch(cfg, active)
            args = launch.call_args.args[1]
            self.assertEqual(args[args.index("-port") + 1], "5556")
            with patch("androidctl.service.os.execv") as proxy:
                service.proxy(cfg, active)
            self.assertIn("TCP4:127.0.0.1:5557", proxy.call_args.args[1])
            with patch("androidctl.service.require_root"):
                service.release(cfg, active)
            self.assertEqual((data / "userdata.img").read_bytes(), b"preserve this disk")
            self.assertEqual(get_instance(cfg, "200").remote_adb_port, 15750)
            self.assertFalse(service.reservation(cfg, "200").exists())
            self.assertTrue((Path(cfg.instance_root) / "200.conf").exists())

    def test_new_cli_flag_allows_large_id_without_altering_legacy_defaults(self):
        from androidctl.cli import parser

        self.assertTrue(parser().parse_args(["create", "200", "--runtime-ports"]).runtime_ports)
        self.assertFalse(parser().parse_args(["create", "01"]).runtime_ports)

    def test_create_200_reserves_disk_and_endpoint_without_starting(self):
        from androidctl import instance
        from androidctl.cli import parser
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as root:
            cfg = Config(
                instance_root=root + "/instances", avd_root=root + "/avd", runtime_root=root + "/run"
            )
            Path(cfg.avd_root).mkdir()
            args = parser().parse_args(["create", "200", "--runtime-ports", "--display-scale", "50"])
            with (
                patch("androidctl.instance.SDK") as sdk,
                patch("androidctl.instance.avd.create") as create_avd,
                patch("androidctl.instance.systemd.gpu_policy"),
                patch("androidctl.instance.systemd.action") as action,
                patch("androidctl.instance.gpu.selection"),
                patch("androidctl.ports.available"),
                patch("androidctl.instance.shutil.disk_usage", return_value=SimpleNamespace(free=10**12)),
            ):
                sdk.return_value.profiles.return_value = [{"id": "pixel_8_pro"}]
                sdk.return_value.installed.return_value = True
                obj = instance.create(cfg, args)
            self.assertEqual(obj.id, "200")
            self.assertEqual(obj.remote_adb_port, 15750)
            self.assertEqual(obj.display_scale, 50)
            self.assertTrue(get_instance(cfg, "200").runtime_ports)
            create_avd.assert_called_once()
            action.assert_not_called()
