import contextlib
import io
import socket
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

from androidctl import avd, gpu, health, instance, ports, service
from androidctl.cli import main, parser
from androidctl.config import Config, Instance, convert, get_instance, instances, load, save
from androidctl.errors import Error
from androidctl.sdk import SDK


def device(ident="01"):
    c, a, r = ports.allocate(ident)
    return Instance(ident, f"Pixel8Pro_API35_{ident}", 35, "pixel_8_pro", "google_apis", c, a, r)


class PortsTest(unittest.TestCase):
    def test_mapping(self):
        for ident, expected in [
            ("01", (5554, 5555, 15551)),
            ("02", (5556, 5557, 15552)),
            ("03", (5558, 5559, 15553)),
            ("10", (5572, 5573, 15560)),
            ("65", (5682, 5683, 15615)),
        ]:
            self.assertEqual(ports.allocate(ident), expected)

    def test_boundary_and_overrides(self):
        for ident in ("0", "-1", "../01", "abc", "66", "999999"):
            with self.assertRaises(Error):
                ports.allocate(ident)
        self.assertEqual(ports.allocate("99", console=5554, remote=16000), (5554, 5555, 16000))
        for c, local, r in [
            (5555, 5556, 16000),
            (5554, 5556, 16000),
            (5554, 5555, 65536),
            (5554, 5555, 5555),
        ]:
            with self.assertRaises(Error):
                ports.validate(c, local, r)

    def test_actual_listener_conflict(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()
            with self.assertRaises(Error) as caught:
                ports.available([sock.getsockname()[1]])
            self.assertEqual(caught.exception.code, 6)

    def test_cross_role_reservation(self):
        other = replace(device("02"), remote_adb_port=5554)
        with self.assertRaises(Error):
            ports.conflicts(device(), [other], 5038)
        with self.assertRaises(Error):
            ports.conflicts(device(), [], 5555)


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.cfg = replace(
            Config(),
            instance_root=str(self.root / "instances"),
            avd_root=str(self.root / "avds"),
            runtime_root=str(self.root / "run"),
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_round_trip(self):
        save(self.root / "global", self.cfg)
        self.assertEqual(load(self.root / "global"), self.cfg)
        save(Path(self.cfg.instance_root) / "01.conf", device(), "instance")
        self.assertEqual(get_instance(self.cfg, "1"), device())

    def test_missing_required_fields(self):
        with self.assertRaises(Error):
            convert(Instance, {"id": "01"})
        with self.assertRaises(Error) as caught:
            get_instance(self.cfg, "01")
        self.assertEqual(caught.exception.code, 3)

    def test_invalid_config(self):
        for changes in (
            {"api": 0},
            {"id": "1"},
            {"architecture": "arm64-v8a"},
            {"cpu_cores": 0},
            {"ram_mb": 0},
            {"name": "../unsafe"},
            {"gpu_pci": "$bad"},
            {"autostart": "maybe"},
            {"unexpected": "x"},
        ):
            with self.subTest(changes=changes), self.assertRaises(Error):
                convert(Instance, asdict(device()) | changes)

    def test_duplicate_identity(self):
        save(Path(self.cfg.instance_root) / "01.conf", device(), "instance")
        save(Path(self.cfg.instance_root) / "02.conf", replace(device("02"), name=device().name), "instance")
        with self.assertRaises(Error):
            instances(self.cfg)

    def test_malformed_ini(self):
        (self.root / "bad").write_text("[androidctl]\ndefault_api = 35\ndefault_api = 34\n")
        with self.assertRaises(Error):
            load(self.root / "bad")

    def test_bind_policy(self):
        for addr in ("0.0.0.0", "8.8.8.8", "::", "hostname"):
            with self.assertRaises(Error):
                replace(self.cfg, bind_address=addr).validate()
        self.assertEqual(replace(self.cfg, bind_address="127.0.0.1").validate().bind_address, "127.0.0.1")

    def test_symlink_data_rejected(self):
        root = Path(self.cfg.avd_root)
        root.mkdir()
        (root / (device().name + ".avd")).symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(Error):
            avd.paths(self.cfg, device())


class LifecycleTest(unittest.TestCase):
    setUp = ConfigTest.setUp
    tearDown = ConfigTest.tearDown

    def test_states(self):
        for active, boot, proxy, expected in [
            ("inactive", False, False, ("stopped", "unknown")),
            ("activating", False, False, ("starting", "degraded")),
            ("active", False, False, ("booting", "degraded")),
            ("active", True, True, ("running", "healthy")),
            ("active", True, False, ("running", "degraded")),
            ("failed", False, False, ("failed", "unhealthy")),
            ("deactivating", False, False, ("stopping", "unknown")),
        ]:
            self.assertEqual(health.classify(active, boot, proxy), expected)

    @patch("androidctl.instance.stop")
    def test_delete_refusal_never_stops_or_erases(self, stop):
        with patch("sys.stdin.isatty", return_value=False), self.assertRaises(Error) as caught:
            instance.delete(self.cfg, device())
        self.assertEqual(caught.exception.code, 11)
        stop.assert_not_called()

    @patch("androidctl.instance.systemd")
    @patch("androidctl.instance.avd.remove")
    @patch("androidctl.instance.stop")
    def test_keep_data(self, stop, remove, sd):
        save(Path(self.cfg.instance_root) / "01.conf", device(), "instance")
        sd.properties.return_value = {"ActiveState": "inactive"}
        instance.delete(self.cfg, device(), yes=True, keep_data=True)
        remove.assert_not_called()
        self.assertFalse((Path(self.cfg.instance_root) / "01.conf").exists())

    @patch("androidctl.service.os.execve")
    @patch("androidctl.service.os.geteuid", return_value=1000)
    @patch("androidctl.service.SDK.tool", return_value="/opt/android-sdk/emulator/emulator")
    def test_launch_preserves_userdata(self, tool, uid, execute):
        service.launch(self.cfg, device())
        args = execute.call_args.args[1]
        self.assertNotIn("-wipe-data", args)
        self.assertIn("-no-snapshot", args)
        self.assertEqual(args[args.index("-port") + 1], "5554")
        self.assertEqual(args[args.index("-accel") + 1], "on")

    @patch("androidctl.service.os.geteuid", return_value=0)
    def test_root_emulator_rejected(self, uid):
        with self.assertRaises(Error):
            service.launch(self.cfg, device())

    @patch("androidctl.service.time.sleep")
    @patch("androidctl.service.os.kill", side_effect=ProcessLookupError)
    @patch("androidctl.service.adb.command")
    def test_stop_sync_then_emulator_exit(self, command, kill, sleep):
        with patch.dict("os.environ", {"MAINPID": "12345"}):
            service.graceful_stop(self.cfg, device())
        self.assertEqual(command.call_args_list[0].args[2], ["shell", "sync"])
        self.assertEqual(command.call_args_list[1].args[2], ["emu", "kill"])
        self.assertFalse(any(c.args[1] == 9 for c in kill.call_args_list))

    @patch("androidctl.instance.systemd")
    def test_stop_uses_intentional_systemd_stop(self, sd):
        sd.properties.return_value = {"ActiveState": "inactive"}
        instance.stop(self.cfg, device())
        sd.action.assert_called_once_with("stop", "01", wait=False)

    @patch("androidctl.service.require_root")
    @patch("androidctl.service.host")
    @patch("androidctl.service.ports.available")
    @patch("androidctl.service.SDK.installed", return_value=True)
    @patch("androidctl.service.systemd.properties")
    def test_autostart_admission_limit(self, props, installed, available, host, root):
        save(Path(self.cfg.instance_root) / "01.conf", device(), "instance")
        other = device("02")
        save(Path(self.cfg.instance_root) / "02.conf", other, "instance")
        avdroot = Path(self.cfg.avd_root)
        (avdroot / (other.name + ".avd")).mkdir(parents=True)
        (avdroot / (other.name + ".avd") / "config.ini").touch()
        (avdroot / (other.name + ".ini")).touch()
        props.return_value = {"ActiveState": "active"}
        host.available_ram.return_value = 64000
        with self.assertRaises(Error) as caught:
            service.preflight(replace(self.cfg, max_running_instances=1), other)
        self.assertEqual(caught.exception.code, 7)
        self.assertFalse(service.reservation(self.cfg, "02").exists())

    @patch("androidctl.service.require_root")
    def test_reservation_release(self, root):
        path = service.reservation(self.cfg, "01")
        path.parent.mkdir()
        path.write_text("{}")
        service.release(self.cfg, device())
        self.assertFalse(path.exists())


class SDKTest(unittest.TestCase):
    def test_backend_package_formats(self):
        package = device().package
        self.assertEqual(SDK.package_arg(package, "android"), "system-images/android-35/google_apis/x86_64")
        self.assertEqual(SDK.package_arg(package, "sdkmanager"), package)

    @patch("androidctl.sdk.run")
    @patch("androidctl.sdk.SDK.tool", return_value="/sdk/avdmanager")
    def test_profile_parser(self, tool, run):
        run.return_value.stdout = 'id: 0 or "pixel_8_pro"\n    Name: Pixel 8 Pro\n---------\nid: 1 or "pixel_7"\n    Name: Pixel 7\n'
        self.assertEqual(
            SDK(Config()).profiles(),
            [{"id": "pixel_8_pro", "name": "Pixel 8 Pro"}, {"id": "pixel_7", "name": "Pixel 7"}],
        )

    @patch("androidctl.sdk.SDK.packages")
    def test_image_discovery_formats(self, packages):
        packages.return_value = "system-images;android-35;google_apis;x86_64 | 1\nsystem-images/android-34/default/x86_64 | 2\nsystem-images;android-35;google_apis;arm64-v8a"
        self.assertEqual(len(SDK(Config()).images()), 2)

    @patch("androidctl.sdk.run")
    @patch("androidctl.sdk.SDK.backend", return_value=("android", ["android", "--sdk=/sdk", "sdk"]))
    def test_current_install_command(self, backend, run):
        SDK(Config()).install([device().package])
        self.assertEqual(
            run.call_args.args[0][-2:], ["install", "system-images/android-35/google_apis/x86_64"]
        )

    @patch("androidctl.sdk.run")
    @patch("androidctl.sdk.SDK.backend", return_value=("sdkmanager", ["sdkmanager", "--sdk_root=/sdk"]))
    def test_legacy_install_command(self, backend, run):
        SDK(Config()).install([device().package])
        self.assertEqual(run.call_args.args[0][-2:], ["--install", device().package])


class GPUTest(unittest.TestCase):
    def test_no_implicit_host_gpu(self):
        with self.assertRaises(Error):
            gpu.selection(replace(device(), gpu_mode="host"))
        self.assertIsNone(gpu.selection(device()))

    @patch("androidctl.gpu.discover")
    def test_reject_proprietary_driver(self, discover):
        pci = "0000:00:02.0"  # synthetic parser fixture, not a deployment default
        discover.return_value = [{"pci": pci, "driver": "nvidia", "render_node": "/dev/dri/renderD128"}]
        with self.assertRaises(Error):
            gpu.selection(replace(device(), gpu_mode="host", gpu_pci=pci))


class CLITest(unittest.TestCase):
    def test_contract_parses(self):
        for command in (
            "version",
            "doctor --json",
            "list --json",
            "status",
            "status 01",
            "create 01 --api 35 --install-image",
            "delete 01 --yes --keep-data",
            "start 01 --force",
            "stop 01",
            "restart 01",
            "enable 01",
            "disable 01",
            "logs 01 --since 10m --follow",
            "shell 01",
            "adb 01 shell getprop",
            "profiles --json",
            "sdk status",
            "sdk images",
            "sdk install-image --api 34",
            "sdk update",
            "gpu list --json",
            "config show",
            "config get dri_prime",
            "config set dri_prime auto",
            "ports",
            "info 01",
            "adb-endpoint 01",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(parser().parse_args(command.split()))

    def test_help_version_and_empty_list(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main([]), 0)
            self.assertEqual(main(["version"]), 0)
        self.assertIn("androidctl", out.getvalue())

    def test_missing_sdk_actionable(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = replace(Config(), sdk_root=temp)
            with self.assertRaises(Error) as caught:
                SDK(cfg).tool("emulator")
            self.assertEqual(caught.exception.code, 5)


if __name__ == "__main__":
    unittest.main()
