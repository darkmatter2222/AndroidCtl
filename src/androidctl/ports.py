import re
import socket

from .errors import Error


def normalize_id(value):
    if not re.fullmatch(r"[0-9]{1,5}", str(value)) or not 1 <= int(value) <= 59985:
        raise Error("ID must be a positive decimal integer between 1 and 59985.")
    return f"{int(value):02d}"


def validate(console, local, remote):
    if console % 2 or not 5554 <= console <= 5682:
        raise Error("Console port must be even and in Google's supported range 5554–5682.")
    if local != console + 1:
        raise Error("Local ADB port must immediately follow the console port.")
    if not 1024 <= remote <= 65535 or remote in (console, local):
        raise Error("Remote ADB port must be distinct and between 1024 and 65535.")
    return console, local, remote


def allocate(value, console_base=5554, remote_base=15550, console=None, remote=None):
    n = int(normalize_id(value))
    c = console if console is not None else console_base + (n - 1) * 2
    r = remote if remote is not None else remote_base + n
    return validate(c, c + 1, r)


def available(ports, address="0.0.0.0"):
    # Wildcard bind also detects listeners on other local IPv4 interfaces.
    # Reuse expired connections, never a live listener: no SO_REUSEPORT.
    # listen() also checks competing sockets that have bound with reuse enabled.
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((address, port))
                sock.listen(1)
            except OSError as exc:
                raise Error(
                    f"TCP port {port} is occupied/unavailable; inspect: sudo ss -ltnp 'sport = :{port}'", 6
                ) from exc


def reserved_ports(instance):
    # Catalog devices reserve only their stable public endpoint while stopped.
    return (
        {instance.remote_adb_port}
        if instance.runtime_ports
        else {instance.console_port, instance.local_adb_port, instance.remote_adb_port}
    )


def conflicts(instance, others, adb_server_port):
    chosen = reserved_ports(instance)
    if adb_server_port in chosen:
        raise Error(f"Port conflicts with managed ADB server {adb_server_port}.", 6)
    for other in others:
        if other.id == instance.id:
            continue
        overlap = chosen & reserved_ports(other)
        if overlap:
            raise Error(f"Ports {sorted(overlap)} reserved by instance {other.id}.", 6)


def runtime_pair(instance, others, adb_server_port, reservations):
    """Choose a free pair under the caller's manager lock; legacy pairs stay fixed."""
    blocked = {adb_server_port, instance.remote_adb_port}
    for other in others:
        if other.id != instance.id:
            blocked.update(reserved_ports(other))
    for ident, record in reservations.items():
        if ident != instance.id and "console_port" in record:
            port = int(record["console_port"])
            blocked.update((port, port + 1))
    for console in range(5554, 5683, 2):
        if console in blocked or console + 1 in blocked:
            continue
        try:
            available((console, console + 1))
        except Error:
            continue
        return console, console + 1
    raise Error("No emulator runtime port pair is available. Stop another instance or free a listener.", 6)
