#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "$0")" && pwd)"
unit="whisplay-grove-dashboard.service"

# Reopening the shortcut restarts the surface so the compositor raises it,
# while still guaranteeing that only one dashboard owns Port.X.
if systemctl --user is-active --quiet "${unit}"; then
    systemctl --user restart "${unit}"
    exit 0
fi

systemctl --user reset-failed "${unit}" 2>/dev/null || true
exec systemd-run --user --collect \
    --unit="${unit%.service}" \
    --property=Restart=on-failure \
    --property=RestartSec=1 \
    --working-directory="${project_dir}" \
    --setenv=XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}" \
    --setenv=WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}" \
    --setenv=DISPLAY="${DISPLAY:-:0}" \
    --setenv=SDL_VIDEODRIVER=wayland \
    "${project_dir}/.venv/bin/whisplay-grove" dashboard
