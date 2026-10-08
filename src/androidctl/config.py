import configparser
import io
import ipaddress
import re
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .errors import Error
from .ports import normalize_id, validate
from .util import atomic_write

GPU_MODES = ("host", "auto", "software", "swiftshader", "lavapipe", "swangle", "swiftshader_indirect")


@dataclass
class Config:
    sdk_root: str = "/opt/android-sdk"
    avd_root: str = "/var/lib/androidctl/avd"
    instance_root: str = "/etc/androidctl/instances"
    runtime_root: str = "/run/androidctl"
    log_root: str = "/var/log/androidctl"
    service_user: str = "androidctl"
    service_home: str = "/var/lib/androidctl"
    bind_address: str = "127.0.0.1"
    default_profile: str = "pixel_8_pro"
    default_api: int = 35
    default_image: str = "google_apis"
    default_ram_mb: int = 4096
    default_cpu_cores: int = 4
    default_disk_size: str = "16G"
    default_gpu_mode: str = "software"
    dri_prime: str = "auto"
    remote_adb_base_port: int = 15550
    console_base_port: int = 5554
    adb_server_port: int = 5038
    max_running_instances: int = 2
    minimum_free_ram_mb: int = 4096
    boot_timeout: int = 300
    stop_timeout: int = 60
    postboot: bool = True
    disable_animations: bool = False
    android_cli: str = "/opt/android-cli/bin/android"
    cmdline_tools_version: str = "15859902"
    cmdline_tools_sha256: str = "4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583"

    def validate(self):
        for key in (
            "sdk_root",
            "avd_root",
            "instance_root",
            "runtime_root",
            "log_root",
            "service_home",
            "android_cli",
        ):
            value = getattr(self, key)
            if not re.fullmatch(r"/[A-Za-z0-9_./-]+", value) or ".." in Path(value).parts or value == "/":
                raise Error(f"{key} requires a safe absolute path without spaces or traversal.")
        if not re.fullmatch(r"[a-z_][a-z0-9_-]*", self.service_user) or self.service_user == "root":
            raise Error("service_user must be a non-root Linux account.")
        if self.bind_address != "auto":
            try:
                address = ipaddress.IPv4Address(self.bind_address)
            except ValueError as exc:
                raise Error("bind_address must be auto or a literal IPv4 address.") from exc
            if (
                not (
                    address.is_loopback
                    or address in ipaddress.ip_network("10.0.0.0/8")
                    or address in ipaddress.ip_network("172.16.0.0/12")
                    or address in ipaddress.ip_network("192.168.0.0/16")
                )
                or address.is_unspecified
            ):
                raise Error("Bind to loopback or a specific RFC1918 LAN address, never wildcard/public.")
        for key in (
            "max_running_instances",
            "boot_timeout",
            "stop_timeout",
            "default_cpu_cores",
            "default_ram_mb",
        ):
            if getattr(self, key) < 1:
                raise Error(f"{key} must be positive.")
        if self.minimum_free_ram_mb < 0 or not 1024 <= self.adb_server_port <= 65535:
            raise Error("Invalid memory reserve or ADB server port.")
        validate(self.console_base_port, self.console_base_port + 1, self.remote_adb_base_port + 1)
        if self.default_gpu_mode not in GPU_MODES:
            raise Error("Unsupported default GPU mode.")
        if not re.fullmatch(r"[0-9]+", self.cmdline_tools_version) or not re.fullmatch(
            r"[a-fA-F0-9]{64}", self.cmdline_tools_sha256
        ):
            raise Error("Command-line tools require a numeric build and SHA-256 checksum.")
        Instance(
            "01",
            "validation",
            self.default_api,
            self.default_profile,
            self.default_image,
            self.console_base_port,
            self.console_base_port + 1,
            self.remote_adb_base_port + 1,
            ram_mb=self.default_ram_mb,
            cpu_cores=self.default_cpu_cores,
            disk_size=self.default_disk_size,
            gpu_mode=self.default_gpu_mode,
            dri_prime=self.dri_prime,
        ).validate()
        return self


@dataclass
class Instance:
    id: str
    name: str
    api: int
    profile: str
    image: str
    console_port: int
    local_adb_port: int
    remote_adb_port: int
    architecture: str = "x86_64"
    ram_mb: int = 4096
    cpu_cores: int = 4
    disk_size: str = "16G"
    gpu_mode: str = "software"
    dri_prime: str = "auto"
    gpu_pci: str = ""
    autostart: bool = False
    native_pixel_display: bool = False
    disable_guest_vulkan: bool = False

    @property
    def package(self):
        return f"system-images;android-{self.api};{self.image};{self.architecture}"

    @property
    def serial(self):
        return f"127.0.0.1:{self.local_adb_port}"

    def validate(self):
        if self.id != normalize_id(self.id):
            raise Error("Instance ID must be canonical (01, 02, …).")
        for key in ("name", "profile", "image"):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", getattr(self, key)):
                raise Error(f"Invalid {key}.")
        if not 21 <= self.api <= 999 or self.architecture != "x86_64":
            raise Error("Use API >=21 and x86_64 images for native x86_64 KVM.")
        validate(self.console_port, self.local_adb_port, self.remote_adb_port)
        if not 512 <= self.ram_mb <= 1048576 or not 1 <= self.cpu_cores <= 1024:
            raise Error("Invalid RAM/CPU allocation.")
        if not re.fullmatch(r"[1-9][0-9]{0,4}[GM]", self.disk_size):
            raise Error("Disk size must be a positive integer followed by G or M.")
        if self.gpu_mode not in GPU_MODES:
            raise Error(f"GPU mode must be one of {GPU_MODES}.")
        if self.gpu_pci and not re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", self.gpu_pci):
            raise Error("gpu_pci requires a full PCI address from androidctl gpu list.")
        if self.dri_prime != "auto" and not re.fullmatch(
            r"pci-[0-9a-f]{4}_[0-9a-f]{2}_[0-9a-f]{2}_[0-7]", self.dri_prime
        ):
            raise Error("dri_prime requires auto or a stable Mesa pci- selector.")
        return self


def convert(cls, values):
    known = {f.name: f.type for f in fields(cls)}
    if set(values) - known.keys():
        raise Error(f"Unknown configuration keys: {sorted(set(values) - known.keys())}")
    result = {}
    try:
        for key, value in values.items():
            if known[key] is bool:
                if str(value).lower() not in ("true", "false"):
                    raise ValueError(f"{key} must be true/false")
                result[key] = str(value).lower() == "true"
            else:
                result[key] = known[key](value)
        return cls(**result).validate()
    except (ValueError, TypeError) as exc:
        raise Error(f"Invalid configuration: {exc}") from exc


def load(path, cls=Config, section="androidctl", required=False):
    p = configparser.ConfigParser(interpolation=None)
    if not Path(path).exists():
        if required:
            raise Error(f"Configuration not found: {path}", 3)
        return cls().validate()
    try:
        p.read(path)
        if section not in p or set(p.sections()) != {section} or p.defaults():
            raise Error(f"Expected only [{section}] in {path}.")
        return convert(cls, dict(p[section]))
    except configparser.Error as exc:
        raise Error(f"Malformed configuration {path}: {exc}") from exc


def save(path, obj, section="androidctl"):
    obj.validate()
    p = configparser.ConfigParser(interpolation=None)
    p[section] = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in asdict(obj).items()}
    buf = io.StringIO()
    p.write(buf)
    atomic_write(path, buf.getvalue())


def instances(cfg):
    result = []
    for path in sorted(Path(cfg.instance_root).glob("*.conf")):
        obj = load(path, Instance, "instance", required=True)
        if path.stem != obj.id or any(i.id == obj.id or i.name == obj.name for i in result):
            raise Error(f"Duplicate ID/name or noncanonical filename: {path}")
        result.append(obj)
    return result


def get_instance(cfg, value):
    ident = normalize_id(value)
    obj = load(Path(cfg.instance_root) / f"{ident}.conf", Instance, "instance", required=True)
    if obj.id != ident:
        raise Error("Configuration ID does not match its filename.")
    return obj
