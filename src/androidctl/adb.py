from .sdk import SDK, environment
from .util import run


def command(cfg, instance, args, *, check=True, capture=True, timeout=15):
    # The explicitly connected loopback transport works above ADB's historical
    # automatic discovery range as well as on current tools.
    return run(
        [SDK(cfg).tool("adb"), "-s", instance.serial] + list(args),
        env=environment(cfg),
        timeout=timeout,
        check=check,
        capture=capture,
    )


def connect(cfg, instance):
    return run(
        [SDK(cfg).tool("adb"), "connect", instance.serial], env=environment(cfg), timeout=10, check=False
    )


def booted(cfg, instance):
    return (
        command(cfg, instance, ["shell", "getprop", "sys.boot_completed"], check=False).stdout.strip() == "1"
    )
