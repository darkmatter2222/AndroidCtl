from .sdk import SDK, client_environment
from .util import run


def command(cfg, instance, args, *, check=True, capture=True, timeout=15):
    # The explicitly connected loopback transport works above ADB's historical
    # automatic discovery range as well as on current tools.
    # `adb emu` resolves the console from an emulator-N serial, not a TCP
    # transport serial. Ordinary device commands retain the explicit transport.
    serial = f"emulator-{instance.console_port}" if args and args[0] == "emu" else instance.serial
    return run(
        [SDK(cfg).tool("adb"), "-s", serial] + list(args),
        env=client_environment(cfg),
        timeout=timeout,
        check=check,
        capture=capture,
    )


def connect(cfg, instance):
    return run(
        [SDK(cfg).tool("adb"), "connect", instance.serial],
        env=client_environment(cfg),
        timeout=10,
        check=False,
    )


def booted(cfg, instance):
    return (
        command(cfg, instance, ["shell", "getprop", "sys.boot_completed"], check=False).stdout.strip() == "1"
    )
