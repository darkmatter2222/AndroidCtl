import runpy
import unittest
from pathlib import Path

validate = runpy.run_path(str(Path(__file__).parents[1] / 'libexec/androidctl-remote'))['validate']


class RemoteGatewayTests(unittest.TestCase):
    def test_supported_web_operations(self):
        cases = [
            ['check'], ['start', '01'], ['stop', '200'], ['restart', '01'],
            ['enable', '01'], ['disable', '01'], ['delete', '01', '--yes', '--keep-data'],
            ['delete', '01', '--yes'], ['renderer', '01', '--gpu', 'host'],
            ['display', '01', '--scale', '33'], ['config', 'set', 'max_running_instances', '3'],
            ['create', '201', '--runtime-ports', '--api', '35', '--ram', '4096', '--cpus', '4',
             '--profile', 'pixel_8_pro', '--image', 'google_apis', '--disk', '16G', '--display-scale', '50'],
        ]
        for case in cases:
            with self.subTest(case=case):
                validate(case)

    def test_reject_privilege_escape_and_unintended_commands(self):
        cases = [[], ['shell', '01'], ['adb', '01', 'shell'], ['_service', 'launch', '01'],
                 ['--config', '/tmp/evil', 'start', '01'], ['start', '01', '--config', '/tmp/evil'],
                 ['config', 'set', 'sdk_root', '/tmp/evil'], ['config', 'set', 'max_running_instances', '66'],
                 ['create', '01', '--install-image'], ['create', '01', '--profile', '../evil'],
                 ['create', '01', '--name', 'x;id'], ['create', '01', '--ram', '4096', '--ram', '8192'],
                 ['start', '0'], ['start', '1;id'], ['delete', '01'], ['check', 'shell'],
                 ['renderer', '01', '--gpu', 'host', '--gpu-pci', 'evil'], ['sdk', 'licenses']]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate(case)
