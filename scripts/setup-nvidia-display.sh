#!/usr/bin/env bash
# Create an authenticated NVIDIA-backed Xorg display for one AndroidCtl instance.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
ident="${1:-01}"
[[ "$ident" =~ ^[0-9]{1,5}$ ]] || { echo 'Expected instance ID 1–59985.' >&2; exit 1; }
printf -v ident '%02d' "$((10#$ident))"
((10#$ident >= 1 && 10#$ident <= 59985)) || exit 1
CTL=/usr/local/bin/androidctl
root=/etc/androidctl/nvidia-xorg
unit=androidctl-nvidia-xorg.service

# Read validated installed configuration, rather than guessing the service identity.
mapfile -t settings < <(/usr/bin/python3 - "$ident" <<'PY'
import sys
sys.path.insert(0, '/usr/local/lib/androidctl')
from androidctl.config import load, get_instance
from androidctl.gpu import selection
cfg = load('/etc/androidctl/androidctl.conf')
obj = get_instance(cfg, sys.argv[1])
if obj.gpu_mode != 'host':
    raise SystemExit('Select --gpu host for the stopped instance first.')
dev = selection(obj)
if dev['driver'] != 'nvidia':
    raise SystemExit('Selected device is not NVIDIA.')
domain, bus, slot = obj.gpu_pci.split(':')
slot, function = slot.split('.')
if int(domain,16) != 0:
    raise SystemExit('This setup currently supports PCI domain 0000 only.')
print(cfg.service_user)
print(f'PCI:{int(bus,16)}:{int(slot,16)}:{int(function,16)}')
PY
)
[[ ${#settings[@]} -eq 2 ]] || { echo 'Could not validate NVIDIA instance configuration.' >&2; exit 1; }
account="${settings[0]}"
busid="${settings[1]}"
group="$(id -gn "$account")"

if ! command -v Xorg >/dev/null || ! command -v xauth >/dev/null || ! command -v glxinfo >/dev/null; then
    apt-get update
    apt-get install -y --no-install-recommends xserver-xorg-core xauth mesa-utils
fi
XORG="$(command -v Xorg)"
[[ -x /usr/lib/xorg/Xorg ]] && XORG=/usr/lib/xorg/Xorg
if ! find /usr/lib -name nvidia_drv.so -print -quit | grep -q .; then
    echo 'NVIDIA Xorg driver module is missing. Install graphics components matching your existing driver.' >&2
    echo 'No NVIDIA driver replacement was attempted.' >&2
    exit 1
fi

if ! systemctl is-active --quiet "$unit"; then
    if [[ -e /tmp/.X99-lock || -S /tmp/.X11-unix/X99 ]]; then
        echo 'Display :99 is occupied or has a stale lock. Refusing to touch it.' >&2
        exit 1
    fi
    install -d -m 0750 -o root -g "$group" "$root"
    if [[ ! -f "$root/Xauthority" ]]; then
        touch "$root/Xauthority"
        chmod 0600 "$root/Xauthority"
        cookie="$(/usr/bin/python3 -c 'import secrets; print(secrets.token_hex(16))')"
        xauth -f "$root/Xauthority" add :99 MIT-MAGIC-COOKIE-1 "$cookie"
        unset cookie
    fi
    chown root:"$group" "$root/Xauthority"
    chmod 0640 "$root/Xauthority"
    cat > "$root/xorg.conf" <<EOF
Section "ServerFlags"
    Option "AutoAddDevices" "false"
    Option "AutoAddGPU" "false"
EndSection
Section "Device"
    Identifier "AndroidCtlNvidia"
    Driver "nvidia"
    BusID "$busid"
    Option "AllowEmptyInitialConfiguration" "true"
    Option "UseDisplayDevice" "none"
EndSection
Section "Screen"
    Identifier "AndroidCtlScreen"
    Device "AndroidCtlNvidia"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Virtual 1920 3200
    EndSubSection
EndSection
Section "ServerLayout"
    Identifier "AndroidCtlLayout"
    Screen "AndroidCtlScreen"
EndSection
EOF
    cat > "/etc/systemd/system/$unit" <<EOF
[Unit]
Description=AndroidCtl NVIDIA headless Xorg display
After=systemd-udev-settle.service
[Service]
Type=simple
ExecStart=$XORG :99 -config $root/xorg.conf -auth $root/Xauthority -nolisten tcp -noreset -novtswitch -sharevts -logfile /var/log/androidctl-nvidia-xorg.log
Restart=on-failure
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl start "$unit"
fi

echo 'Checking OpenGL as the Android service account...'
report=""
for _attempt in {1..20}; do
    if report="$(timeout 5 runuser -u "$account" -- env DISPLAY=:99 XAUTHORITY="$root/Xauthority" __GLX_VENDOR_LIBRARY_NAME=nvidia glxinfo -B 2>&1)"; then
        break
    fi
    sleep 1
done
printf '%s\n' "$report"
if ! grep -Eq 'OpenGL renderer string:.*NVIDIA' <<< "$report"; then
    echo 'NVIDIA GLX validation failed; Android was not started.' >&2
    journalctl -u "$unit" -n 60 --no-pager
    tail -n 60 /var/log/androidctl-nvidia-xorg.log || true
    exit 1
fi

systemctl stop "android-emulator@$ident.service" "android-adb-proxy@$ident.service"
install -d "/etc/systemd/system/android-emulator@$ident.service.d"
cat > "/etc/systemd/system/android-emulator@$ident.service.d/nvidia-display.conf" <<EOF
[Unit]
Requires=$unit
After=$unit
[Service]
Environment=DISPLAY=:99
Environment=XAUTHORITY=$root/Xauthority
# The Xorg Unix socket must be visible to this service.
PrivateTmp=false
EOF
systemctl daemon-reload
systemctl reset-failed "android-emulator@$ident.service" || true
if ! "$CTL" start "$ident"; then
    journalctl -u "android-emulator@$ident.service" -n 100 --no-pager
    exit 1
fi
"$CTL" status "$ident" --json
nvidia-smi
printf '\nDisplay configured and instance %s booted. Test actual app responsiveness next.\n' "$ident"
