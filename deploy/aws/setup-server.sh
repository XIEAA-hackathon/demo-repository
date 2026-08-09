#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT=/opt/casino_hackathon
ENV_DIR=/etc/casino-hackathon
ENV_FILE="$ENV_DIR/backend.env"

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo." >&2
  exit 1
fi
. /etc/os-release
if [[ $ID != amzn ]]; then
  echo "This production setup targets Amazon Linux 2023." >&2
  exit 1
fi
app_user=${SUDO_USER:-ec2-user}
app_group=$(id -gn "$app_user")

dnf install -y ca-certificates curl nginx openssl python3 python3-pip rsync tar gzip
install -d -o "$app_user" -g "$app_group" -m 0755 "$APP_ROOT" "$APP_ROOT/releases"
install -d -o "$app_user" -g "$app_group" -m 2770 "$APP_ROOT/data"
install -d -o root -g root -m 0750 "$ENV_DIR"

if [[ ! -f $ENV_FILE ]]; then
  secret_key=$(openssl rand -hex 48)
  admin_password=$(openssl rand -hex 18)
  umask 077
  printf '%s\n' \
    'DATABASE_URL=sqlite:////opt/casino_hackathon/data/casino_hackathon.db' \
    "SECRET_KEY=$secret_key" \
    'ALGORITHM=HS256' \
    'ACCESS_TOKEN_EXPIRE_MINUTES=1440' \
    'CORS_ORIGINS=http://localhost' \
    'ADMIN_EMAIL=admin@example.com' \
    "ADMIN_PASSWORD=$admin_password" \
    'ADMIN_NAME=Event Admin' > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "Created the production environment with generated secrets; values were not printed."
else
  echo "Preserved existing $ENV_FILE."
fi

systemctl enable nginx
echo "Amazon Linux server prerequisites are ready."
