import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from androidctl import fleet, service
from androidctl.config import Config, Instance
from androidctl.errors import Error


class FleetTests(unittest.TestCase):
    def obj(self):
        return Instance(
            "01",
            "Pixel",
            35,
            "pixel_8_pro",
            "google_apis",
            5554,
            5555,
            15551,
            native_pixel_display=True,
            disable_guest_vulkan=True,
            gpu_mode="swangle",
        )

    def test_ids_are_normalized_deduplicated_and_bounded(self):
        self.assertEqual(fleet.selected(["1", "01", "4"]), ["01", "04"])
        with self.assertRaises(Error):
            fleet.selected(["05"])

    @patch("androidctl.fleet.run")
    @patch("androidctl.fleet.systemd.gpu_policy")
    @patch("androidctl.fleet.systemd.properties", return_value={"ActiveState": "active"})
    @patch("androidctl.fleet.get_instance")
    def test_start_queues_all_units_without_waiting_or_restarting_active(self, get, props, policy, run):
        get.side_effect = lambda cfg, ident: SimpleNamespace(id=ident)
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(runtime_root=tmp)
            fleet.dispatch(cfg, SimpleNamespace(action="start", ids=[]))
        run.assert_called_once_with(
            ["systemctl", "start", "--no-block", *[f"android-emulator@{i}.service" for i in fleet.IDS]]
        )

    @patch("androidctl.service.os.execve")
    @patch("androidctl.service.os.geteuid", return_value=999)
    @patch("androidctl.service.SDK")
    def test_launch_native_dimensions_and_per_instance_vulkan(self, sdk, uid, execute):
        sdk.return_value.tool.return_value = "/emulator"
        service.launch(Config(), self.obj())
        args = execute.call_args.args[1]
        self.assertEqual(args[args.index("-skin") + 1], "1344x2992")
        self.assertEqual(args[args.index("-feature") + 1], "-Vulkan")
        self.assertNotIn("-wipe-data", args)

    @patch("androidctl.service.adb.connect")
    @patch("androidctl.service.adb.booted", return_value=True)
    @patch("androidctl.service.adb.command")
    def test_postboot_resets_old_overrides_even_without_optional_settings(self, command, booted, connect):
        command.return_value = SimpleNamespace(stdout="Physical size: 1344x2992\n")
        service.postboot(Config(postboot=False), self.obj())
        calls = [c.args[2] for c in command.call_args_list]
        self.assertIn(["shell", "wm", "size", "reset"], calls)
        self.assertIn(["shell", "wm", "density", "reset"], calls)
        command.return_value.stdout = "Physical size: 1344x2992\nOverride size: 672x1496"
        with self.assertRaises(Error):
            service.postboot(Config(postboot=False), self.obj())

    @patch("androidctl.fleet.pwd.getpwnam")
    @patch("androidctl.fleet.os.chown")
    def test_display_edit_preserves_userdata_and_unrelated_config(self, chown, account):
        account.return_value = SimpleNamespace(pw_uid=999, pw_gid=999)
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(avd_root=tmp)
            directory = Path(tmp) / "Pixel.avd"
            directory.mkdir()
            (directory / "config.ini").write_text("custom.key=keep\nhw.lcd.width=672\n")
            (directory / "userdata-qemu.img").write_bytes(b"preserve")
            fleet.configure_display(cfg, self.obj())
            text = (directory / "config.ini").read_text()
            self.assertIn("hw.lcd.width=1344", text)
            self.assertIn("hw.lcd.height=2992", text)
            self.assertIn("custom.key=keep", text)
            self.assertEqual((directory / "userdata-qemu.img").read_bytes(), b"preserve")
            self.assertEqual(len(list(directory.glob("config.ini.backup-*"))), 1)

    @patch("androidctl.fleet.get_instance", side_effect=Error("missing"))
    def test_monitor_missing_device_is_an_event_not_fatal(self, get):
        self.assertEqual(fleet.snapshot(Config(), "04")["state"], "unavailable")
