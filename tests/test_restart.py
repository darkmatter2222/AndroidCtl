import socket
import unittest
from unittest.mock import patch

from androidctl import adb, ports
from androidctl.config import Config
from androidctl.errors import Error
from test_core import device


class RestartTest(unittest.TestCase):
    def test_time_wait_does_not_block_restart(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            listener.listen(1)
            with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                accepted, _ = listener.accept()
                accepted.close()  # server actively closes, creating server TIME_WAIT
                self.assertEqual(client.recv(1), b"")
        # Demonstrate the original bug with a real closed connection.
        with socket.socket() as old_probe:
            with self.assertRaises(OSError):
                old_probe.bind(("0.0.0.0", port))
        ports.available([port])
        ports.available([port], address="127.0.0.1")

    def test_live_reusable_listener_is_still_rejected(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            with self.assertRaises(Error) as caught:
                ports.available([listener.getsockname()[1]])
            self.assertEqual(caught.exception.code, 6)

    @patch("androidctl.adb.run")
    @patch("androidctl.adb.SDK.tool", return_value="/sdk/adb")
    def test_shutdown_targets_emulator_console(self, tool, run):
        adb.command(Config(), device(), ["emu", "kill"])
        self.assertEqual(run.call_args.args[0], ["/sdk/adb", "-s", "emulator-5554", "emu", "kill"])
        adb.command(Config(), device(), ["shell", "sync"])
        self.assertEqual(run.call_args.args[0][2], "127.0.0.1:5555")


if __name__ == "__main__":
    unittest.main()
