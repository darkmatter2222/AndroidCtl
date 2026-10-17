import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('install_permissions', Path(__file__).parents[1] / 'scripts/install_permissions.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PermissionTests(unittest.TestCase):
    def test_group_writable_checkout_modes_are_normalized(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'application'
            root.mkdir(mode=0o775)
            file = root / 'code.py'
            file.write_text('pass\n')
            file.chmod(0o664)
            executable = root / 'launcher'
            executable.write_text('#!/bin/sh\n')
            executable.chmod(0o775)
            with patch.object(module.os, 'chown') as chown:
                module.secure_tree(root)
            self.assertEqual(root.stat().st_mode & 0o777, 0o755)
            self.assertEqual(file.stat().st_mode & 0o777, 0o644)
            self.assertEqual(executable.stat().st_mode & 0o777, 0o755)
            self.assertEqual(chown.call_count, 3)
            self.assertTrue(all(c.args[1:] == (0, 0) for c in chown.call_args_list))

    def test_symlink_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'application'
            root.mkdir()
            (root / 'link').symlink_to('/etc/passwd')
            with patch.object(module.os, 'chown') as chown, self.assertRaises(ValueError):
                module.secure_tree(root)
            chown.assert_not_called()
