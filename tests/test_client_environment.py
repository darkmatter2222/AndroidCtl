from types import SimpleNamespace
import unittest
from unittest.mock import patch

from androidctl import adb
from androidctl.config import Config
from androidctl.sdk import client_environment, environment
from test_core import device


class ClientEnvironmentTest(unittest.TestCase):
    @patch("androidctl.sdk.pwd.getpwuid")
    def test_normal_user_keeps_own_home_and_managed_endpoint(self, account):
        account.return_value = SimpleNamespace(pw_name="test_operator", pw_dir="/home/test_operator")
        env = client_environment(Config())
        self.assertEqual(env["HOME"], "/home/test_operator")
        self.assertEqual(env["ANDROID_USER_HOME"], "/home/test_operator/.android")
        self.assertEqual(env["ADB_SERVER_SOCKET"], "tcp:5038")

    @patch("androidctl.sdk.pwd.getpwuid")
    def test_service_account_retains_configured_home(self, account):
        account.return_value = SimpleNamespace(pw_name="androidctl", pw_dir="/nonexistent")
        self.assertEqual(client_environment(Config())["HOME"], "/var/lib/androidctl")

    @patch("androidctl.sdk.pwd.getpwuid")
    def test_root_client_does_not_write_service_preferences(self, account):
        account.return_value = SimpleNamespace(pw_name="root", pw_dir="/root")
        self.assertEqual(client_environment(Config())["ANDROID_USER_HOME"], "/root/.android")
        self.assertEqual(environment(Config())["ANDROID_USER_HOME"], "/var/lib/androidctl/.android")

    @patch("androidctl.adb.run")
    @patch("androidctl.adb.SDK.tool", return_value="/sdk/adb")
    @patch("androidctl.sdk.pwd.getpwuid")
    def test_adb_command_and_connect_use_client_environment(self, account, tool, run):
        account.return_value = SimpleNamespace(pw_name="test_operator", pw_dir="/home/test_operator")
        for call in (
            lambda: adb.command(Config(), device(), ["get-state"]),
            lambda: adb.connect(Config(), device()),
        ):
            call()
            self.assertEqual(run.call_args.kwargs["env"]["ANDROID_USER_HOME"], "/home/test_operator/.android")
            self.assertEqual(run.call_args.kwargs["env"]["ADB_SERVER_SOCKET"], "tcp:5038")


if __name__ == "__main__":
    unittest.main()
