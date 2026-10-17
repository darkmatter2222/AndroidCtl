import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from androidctl import display, service
from androidctl.config import Config, Instance, load
from androidctl.errors import Error


class DisplayTests(unittest.TestCase):
    def setUp(self):
        self.obj = Instance("01", "phone", 35, "pixel_8_pro", "google_apis", 5554, 5555, 15551)

    def test_scale_uses_physical_dimensions_not_existing_override(self):
        obj = replace(self.obj, display_scale=50)
        with patch("androidctl.display.adb.command") as command:
            command.side_effect = [
                SimpleNamespace(stdout="Physical size: 1344x2992\nOverride size: 336x748"),
                SimpleNamespace(stdout="Physical density: 480\nOverride density: 120"),
                None,
                None,
            ]
            display.apply(Config(), obj)
        self.assertEqual(command.call_args_list[2].args[2], ["shell", "wm", "size", "672x1496"])
        self.assertEqual(command.call_args_list[3].args[2], ["shell", "wm", "density", "240"])

    def test_native_resets_both_overrides(self):
        with patch("androidctl.display.adb.command") as command:
            command.side_effect = [
                SimpleNamespace(stdout="Physical size: 1344x2992"),
                SimpleNamespace(stdout="Physical density: 480"),
                None,
                None,
            ]
            display.apply(Config(), replace(self.obj, display_scale=100))
        self.assertEqual(command.call_args_list[2].args[2][-1], "reset")
        self.assertEqual(command.call_args_list[3].args[2][-1], "reset")

    def test_stopped_policy_persists_without_adb(self):
        with tempfile.TemporaryDirectory() as root:
            cfg = Config(instance_root=root)
            with (
                patch("androidctl.display.lock"),
                patch("androidctl.display.systemd.properties", return_value={"ActiveState": "inactive"}),
                patch("androidctl.display.apply") as apply,
            ):
                display.configure(cfg, replace(self.obj, native_pixel_display=True), 33)
            restored = load(Path(root) / "01.conf", Instance, "instance", required=True)
            self.assertEqual(restored.display_scale, 33)
            self.assertTrue(restored.native_pixel_display)
            apply.assert_not_called()

    def test_policy_reapplied_on_service_boot_even_without_other_tuning(self):
        cfg = Config(postboot=False)
        obj = replace(self.obj, display_scale=25)
        with (
            patch("androidctl.service.adb.connect"),
            patch("androidctl.service.adb.booted", return_value=True),
            patch("androidctl.display.apply") as apply,
        ):
            service.postboot(cfg, obj)
        apply.assert_called_once_with(cfg, obj)

    def test_invalid_scale_and_transition_rejected(self):
        with self.assertRaises(Error):
            display.configure(Config(), self.obj, 17)
        with (
            patch("androidctl.display.lock"),
            patch("androidctl.display.systemd.properties", return_value={"ActiveState": "activating"}),
            patch("androidctl.display.save") as save,
        ):
            with self.assertRaises(Error):
                display.configure(Config(), self.obj, 50)
            save.assert_not_called()

    def test_launch_does_not_apply_policy_before_android_exists(self):
        obj = replace(self.obj, display_scale=50, native_pixel_display=True)
        with (
            patch("androidctl.service.os.execve") as execute,
            patch("androidctl.service.os.geteuid", return_value=999),
            patch("androidctl.service.SDK") as sdk,
            patch("androidctl.display.apply") as apply,
        ):
            sdk.return_value.tool.return_value = "/emulator"
            service.launch(Config(), obj)
        apply.assert_not_called()
        args = execute.call_args.args[1]
        self.assertEqual(args[args.index("-skin") + 1], "1344x2992")
