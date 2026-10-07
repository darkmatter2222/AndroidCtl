import argparse
from dataclasses import replace
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from androidctl.config import Config
from androidctl.errors import Error

spec = importlib.util.spec_from_file_location(
    "deploy", Path(__file__).resolve().parents[1] / "scripts/deploy.py"
)
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DeployTest(unittest.TestCase):
    def test_refuses_install_without_kvm_before_package_mutations(self):
        args = argparse.Namespace(user=None, accept_licenses=False)
        with (
            patch.object(deploy, "load", return_value=Config()),
            patch.object(deploy.platform, "machine", return_value="x86_64"),
            patch.object(
                deploy.platform,
                "freedesktop_os_release",
                return_value={"ID": "ubuntu", "VERSION_ID": "24.04"},
            ),
            patch.object(deploy.Path, "is_dir", return_value=False),
            patch.object(deploy, "run") as run,
        ):
            with self.assertRaises(Error):
                deploy.install(args)
            run.assert_not_called()

    def test_purge_refuses_without_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = replace(Config(), runtime_root=temp)
            args = argparse.Namespace(purge=True, yes=False)
            with (
                patch.object(deploy, "load", return_value=cfg),
                patch.object(deploy, "assert_stopped"),
                patch.object(deploy.sys.stdin, "isatty", return_value=False),
                patch.object(deploy.shutil, "rmtree") as remove,
            ):
                with self.assertRaises(Error) as caught:
                    deploy.uninstall(args)
                self.assertEqual(caught.exception.code, 11)
                remove.assert_not_called()

    def test_archive_hash_verified_before_extract(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = replace(Config(), sdk_root=temp, cmdline_tools_sha256="0" * 64)

            def download(url, path):
                Path(path).write_bytes(b"not a trusted zip")

            with patch.object(deploy.urllib.request, "urlretrieve", side_effect=download):
                with self.assertRaisesRegex(Error, "SHA-256"):
                    deploy.bootstrap_sdk(cfg)
            self.assertFalse((Path(temp) / "cmdline-tools").exists())

    def test_verified_zip_layout_and_executable_modes(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "fixture.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("cmdline-tools/bin/sdkmanager", "#!/bin/sh\nexit 0\n")
                z.writestr("cmdline-tools/bin/avdmanager", "#!/bin/sh\nexit 0\n")
            cfg = replace(
                Config(),
                sdk_root=str(Path(temp) / "sdk"),
                cmdline_tools_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
            )

            def download(url, path):
                Path(path).write_bytes(archive.read_bytes())

            with patch.object(deploy.urllib.request, "urlretrieve", side_effect=download):
                deploy.bootstrap_sdk(cfg)
            binary = Path(cfg.sdk_root) / "cmdline-tools/latest/bin/sdkmanager"
            self.assertTrue(binary.is_file())
            self.assertEqual(binary.stat().st_mode & 0o777, 0o755)


if __name__ == "__main__":
    unittest.main()
