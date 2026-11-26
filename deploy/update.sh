#!/usr/bin/env bash
# Actualiza el servidor con lo último de GitHub (no toca datos ni .env):
#   sudo bash /opt/reportecax/deploy/update.sh
set -euo pipefail
APP_DIR=/opt/reportecax
APP_USER=reportecax

sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt" gunicorn
chmod -R o+rX "$APP_DIR/static"
systemctl restart reportecax.service
echo "Actualizado."
