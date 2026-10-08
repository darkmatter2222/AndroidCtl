"""Validate rendered unit syntax without installing or starting anything."""

from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[1]
values = {
    "SERVICE_USER": "androidctl",
    "SERVICE_GROUP": "androidctl",
    "SERVICE_HOME": "/var/lib/androidctl",
    "AVD_ROOT": "/var/lib/androidctl/avd",
    "RUNTIME_ROOT": "/run/androidctl",
    "LOG_ROOT": "/var/log/androidctl",
    "START_TIMEOUT": "360",
    "STOP_TIMEOUT": "100",
}
with tempfile.TemporaryDirectory() as temp:
    paths = []
    for source in (repo / "systemd").glob("*.service"):
        text = source.read_text()
        for key, value in values.items():
            text = text.replace(f"@{key}@", value)
        assert "@SERVICE_" not in text
        text = text.replace("/usr/local/bin/androidctl", "/usr/bin/true")
        path = Path(temp) / source.name
        path.write_text(text)
        paths.append(str(path))
    result = subprocess.run(["systemd-analyze", "verify", *paths], check=False)
    raise SystemExit(result.returncode)
