#!/usr/bin/env bash
# Install the Grove Sensor Hub demo and its desktop launcher.
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="${WHISPLAY_GROVE_INSTALL_DIR:-/opt/whisplay-grove-sensors}"
DESKTOP_USER="${SUDO_USER:-}"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --desktop-user)
            DESKTOP_USER="${2:?--desktop-user requires a user name}"
            shift 2
            ;;
        --install-dir)
            INSTALL_DIR="${2:?--install-dir requires a path}"
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo: sudo ./install.sh" >&2
    exit 1
fi

if [ -z "$DESKTOP_USER" ] || [ "$DESKTOP_USER" = "root" ]; then
    DESKTOP_USER="$(getent passwd 1000 | cut -d: -f1)"
fi
if [ -z "$DESKTOP_USER" ] || ! id "$DESKTOP_USER" >/dev/null 2>&1; then
    echo "Cannot determine the desktop user; pass --desktop-user USER." >&2
    exit 1
fi

DESKTOP_HOME="$(getent passwd "$DESKTOP_USER" | cut -d: -f6)"
DESKTOP_GROUP="$(id -gn "$DESKTOP_USER")"
if [ -z "$DESKTOP_HOME" ] || [ ! -d "$DESKTOP_HOME" ]; then
    echo "Desktop home not found for $DESKTOP_USER." >&2
    exit 1
fi

echo "Installing Grove Sensor Hub to $INSTALL_DIR for $DESKTOP_USER..."
apt-get install -y \
    python3-venv python3-setuptools python3-smbus python3-serial \
    python3-pygame sox >/dev/null

install -d -m 0755 "$INSTALL_DIR"
install -d -m 0755 "$INSTALL_DIR/src" "$INSTALL_DIR/assets" \
    "$INSTALL_DIR/examples" "$INSTALL_DIR/docs"
cp -a "$SOURCE_DIR/src/." "$INSTALL_DIR/src/"
cp -a "$SOURCE_DIR/assets/." "$INSTALL_DIR/assets/"
cp -a "$SOURCE_DIR/examples/." "$INSTALL_DIR/examples/"
cp -a "$SOURCE_DIR/docs/." "$INSTALL_DIR/docs/"
install -m 0644 "$SOURCE_DIR/pyproject.toml" "$INSTALL_DIR/pyproject.toml"
install -m 0644 "$SOURCE_DIR/README.md" "$INSTALL_DIR/README.md"
install -m 0644 "$SOURCE_DIR/LICENSE" "$INSTALL_DIR/LICENSE"
install -m 0755 "$SOURCE_DIR/run-dashboard.sh" "$INSTALL_DIR/run-dashboard.sh"
install -m 0755 "$SOURCE_DIR/install.sh" "$INSTALL_DIR/install.sh"
install -m 0644 "$SOURCE_DIR/whisplay-grove-sensors.desktop" \
    "$INSTALL_DIR/whisplay-grove-sensors.desktop"

if [ ! -x "$INSTALL_DIR/.venv/bin/python" ]; then
    python3 -m venv --system-site-packages "$INSTALL_DIR/.venv"
fi
if ! "$INSTALL_DIR/.venv/bin/pip" install \
        --no-build-isolation --no-deps -e "$INSTALL_DIR" >/dev/null; then
    "$INSTALL_DIR/.venv/bin/pip" install --no-deps -e "$INSTALL_DIR" >/dev/null
fi

desktop_tmp="$(mktemp)"
trap 'rm -f "$desktop_tmp"' EXIT
sed "s|/home/pi/whisplay-grove-sensors|$INSTALL_DIR|g" \
    "$SOURCE_DIR/whisplay-grove-sensors.desktop" > "$desktop_tmp"

install -m 0644 "$desktop_tmp" /usr/share/applications/whisplay-grove-sensors.desktop
install -d -m 0755 -o "$DESKTOP_USER" -g "$DESKTOP_GROUP" \
    "$DESKTOP_HOME/Desktop" "$DESKTOP_HOME/.local/share/applications"
install -m 0755 -o "$DESKTOP_USER" -g "$DESKTOP_GROUP" "$desktop_tmp" \
    "$DESKTOP_HOME/Desktop/05-Grove-Sensor-Hub.desktop"
install -m 0644 -o "$DESKTOP_USER" -g "$DESKTOP_GROUP" "$desktop_tmp" \
    "$DESKTOP_HOME/.local/share/applications/whisplay-grove-sensors.desktop"

for group in i2c dialout audio gpio; do
    if getent group "$group" >/dev/null; then
        usermod -a -G "$group" "$DESKTOP_USER"
    fi
done

if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate /usr/share/applications/whisplay-grove-sensors.desktop
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
    sudo -u "$DESKTOP_USER" update-desktop-database \
        "$DESKTOP_HOME/.local/share/applications" >/dev/null 2>&1 || true
fi

echo "Grove Sensor Hub installed."
echo "Desktop shortcut: $DESKTOP_HOME/Desktop/05-Grove-Sensor-Hub.desktop"
echo "Command: $INSTALL_DIR/run-dashboard.sh"
