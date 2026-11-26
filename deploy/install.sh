#!/usr/bin/env bash
# =============================================================================
# Instala Ciudad Inteligente · Cajamarca en un servidor Ubuntu (Oracle Cloud
# Always Free u otro). Ejecutar como root:
#
#   curl -fsSL https://raw.githubusercontent.com/PILLINBOT/Sistema-ReporteCAX/main/deploy/install.sh | sudo bash
#
# Si antes copiaste tu archivo .env a /tmp/reportecax.env, se usa ese.
# Se puede ejecutar varias veces: no borra datos.
# =============================================================================
set -euo pipefail

REPO="${REPO:-https://github.com/PILLINBOT/Sistema-ReporteCAX.git}"
BRANCH="${BRANCH:-main}"
APP_DIR=/opt/reportecax
DATA_DIR=/var/lib/reportecax
APP_USER=reportecax

[ "$(id -u)" -eq 0 ] || { echo "Ejecuta este script con sudo."; exit 1; }
command -v apt-get >/dev/null || { echo "Este script es para Ubuntu/Debian."; exit 1; }

echo "[1/7] Instalando paquetes del sistema..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git nginx >/dev/null

echo "[2/7] Descargando el código..."
id "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
if [ -d "$APP_DIR/.git" ]; then
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only -q
else
  git clone -q --branch "$BRANCH" "$REPO" "$APP_DIR"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
fi

echo "[3/7] Instalando dependencias de Python..."
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt" gunicorn

echo "[4/7] Configurando datos y .env..."
mkdir -p "$DATA_DIR" "$APP_DIR/static/uploads"
for f in users.json reports.json missions.json; do
  [ -f "$DATA_DIR/$f" ] || cp "$APP_DIR/data/$f" "$DATA_DIR/$f"
done
if [ -f /tmp/reportecax.env ]; then
  mv /tmp/reportecax.env "$APP_DIR/.env"
elif [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo "   AVISO: no había .env; edita $APP_DIR/.env con los datos del correo."
fi
grep -q '^DATA_DIR=' "$APP_DIR/.env" || echo "DATA_DIR=$DATA_DIR" >> "$APP_DIR/.env"
grep -q '^SECRET_KEY=' "$APP_DIR/.env" || echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> "$APP_DIR/.env"
chown -R "$APP_USER:$APP_USER" "$APP_DIR" "$DATA_DIR"
chmod 600 "$APP_DIR/.env"

echo "[5/7] Creando servicios (web 24/7 + correo diario 21:00 Perú)..."
cat > /etc/systemd/system/reportecax.service <<EOF
[Unit]
Description=Ciudad Inteligente Cajamarca (web)
After=network.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/gunicorn --workers 1 --threads 4 --bind 127.0.0.1:8000 wsgi:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/reportecax-report.service <<EOF
[Unit]
Description=Ciudad Inteligente Cajamarca (envío del reporte diario por correo)

[Service]
Type=oneshot
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/enviar_reporte.py
EOF

cat > /etc/systemd/system/reportecax-report.timer <<EOF
[Unit]
Description=Reporte diario a las 21:00 hora de Perú

[Timer]
OnCalendar=*-*-* 21:00:00 America/Lima
Persistent=true

[Install]
WantedBy=timers.target
EOF

echo "[6/7] Configurando nginx..."
cat > /etc/nginx/sites-available/reportecax <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    client_max_body_size 10M;

    location /static/ {
        alias $APP_DIR/static/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
ln -sf /etc/nginx/sites-available/reportecax /etc/nginx/sites-enabled/reportecax
rm -f /etc/nginx/sites-enabled/default
# nginx (www-data) necesita poder leer los archivos estáticos
chmod o+x "$APP_DIR"
chmod -R o+rX "$APP_DIR/static"
nginx -t -q

echo "[7/7] Abriendo el puerto 80 y arrancando..."
# Las imágenes Ubuntu de Oracle bloquean el puerto 80 con iptables.
if ! iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; then
  iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
fi
if command -v netfilter-persistent >/dev/null; then
  netfilter-persistent save >/dev/null 2>&1 || true
fi

systemctl daemon-reload
systemctl enable --now reportecax.service reportecax-report.timer >/dev/null
systemctl restart reportecax.service nginx

sleep 3
IP=$(curl -fsS https://ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
if curl -fsS -o /dev/null http://127.0.0.1/; then
  echo ""
  echo "LISTO. El sistema está en: http://$IP"
  echo "Próximo correo diario: $(systemctl list-timers reportecax-report.timer --no-pager | sed -n 2p | awk '{print $1, $2, $3}')"
else
  echo "El servicio no respondió. Revisa: journalctl -u reportecax -n 50"
  exit 1
fi
