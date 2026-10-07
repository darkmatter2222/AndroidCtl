from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from androidctl import instance, service
from androidctl.cli import parser
from androidctl.config import Config, get_instance, save
from androidctl.errors import Error
from test_core import device


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.cfg = replace(
            Config(),
            instance_root=str(root / "instances"),
            avd_root=str(root / "avd"),
            runtime_root=str(root / "run"),
        )
        Path(self.cfg.avd_root).mkdir()

    @patch("androidctl.service.os.execve")
    @patch("androidctl.service.SDK.tool", return_value="/sdk/adb")
    def test_adb_server_uses_compatible_loopback_listener(self, tool, execute):
        service.adb_server(self.cfg)
        binary, args, env = execute.call_args.args
        self.assertEqual(args, ["/sdk/adb", "-L", "tcp:5038", "server", "nodaemon"])
        self.assertNotIn("-a", args)
        self.assertEqual(env["ADB_SERVER_SOCKET"], "tcp:5038")
        self.assertEqual(env["ANDROID_ADB_SERVER_PORT"], "5038")

    @patch("androidctl.instance.shutil.disk_usage")
    @patch("androidctl.instance.systemd.gpu_policy")
    @patch("androidctl.instance.avd.create")
    @patch("androidctl.instance.SDK")
    @patch("androidctl.instance.ports.available")
    def test_create_two_apis_has_independent_paths_ports_and_configs(
        self, available, sdk, create, policy, disk
    ):
        sdk.return_value.profiles.return_value = [{"id": "pixel_8_pro", "name": "Pixel 8 Pro"}]
        sdk.return_value.installed.return_value = True
        disk.return_value.free = 100 * 1024**3
        first = instance.create(self.cfg, parser().parse_args("create 01 --api 35".split()))
        second = instance.create(self.cfg, parser().parse_args("create 02 --api 34".split()))
        self.assertEqual((first.name, second.name), ("Pixel8Pro_API35_01", "Pixel8Pro_API34_02"))
        self.assertNotEqual(first.console_port, second.console_port)
        self.assertEqual(get_instance(self.cfg, "02").api, 34)
        self.assertFalse(first.autostart)
        self.assertEqual(create.call_count, 2)
        sdk.return_value.install.assert_not_called()

    @patch("androidctl.instance.avd.create")
    def test_duplicate_create_never_touches_avd(self, create):
        save(Path(self.cfg.instance_root) / "01.conf", device(), "instance")
        with self.assertRaises(Error) as caught:
            instance.create(self.cfg, parser().parse_args("create 1".split()))
        self.assertEqual(caught.exception.code, 4)
        create.assert_not_called()

    @patch("androidctl.instance.avd.create")
    def test_zero_api_is_rejected_not_defaulted(self, create):
        with self.assertRaises(Error):
            instance.create(self.cfg, parser().parse_args("create 01 --api 0".split()))
        create.assert_not_called()

    @patch("androidctl.instance.time.sleep")
    @patch("androidctl.instance.status")
    @patch("androidctl.instance.systemd")
    def test_start_waits_for_boot_and_proxy_health(self, sd, status, sleep):
        sd.properties.return_value = {"ActiveState": "inactive"}
        status.side_effect = [
            {"state": "starting", "health": "degraded"},
            {"state": "running", "health": "healthy"},
        ]
        self.assertEqual(instance.start(self.cfg, device())["health"], "healthy")
        sd.action.assert_called_once_with("start", "01", wait=False)
        self.assertEqual(status.call_count, 2)

    @patch("androidctl.service.time.sleep")
    @patch("androidctl.service.adb")
    def test_postboot_does_not_apply_settings_until_boot_complete(self, adb, sleep):
        adb.booted.side_effect = [False, True]
        service.postboot(self.cfg, device())
        self.assertEqual(adb.booted.call_count, 2)
        self.assertEqual(
            adb.command.call_args_list[0].args[2],
            ["shell", "settings", "put", "global", "development_settings_enabled", "1"],
        )

    @patch("androidctl.service.time.monotonic", side_effect=[0, 9999])
    @patch("androidctl.service.adb")
    def test_postboot_timeout_applies_no_settings(self, adb, clock):
        with self.assertRaises(Error) as caught:
            service.postboot(self.cfg, device())
        self.assertEqual(caught.exception.code, 9)
        adb.command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
