#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT=/opt/casino_hackathon
RELEASES_DIR="$APP_ROOT/releases"
CURRENT_LINK="$APP_ROOT/current"
ENV_FILE=/etc/casino-hackathon/backend.env

archive=${1:?Usage: deploy-release.sh ARCHIVE SHA}
sha=${2:?Usage: deploy-release.sh ARCHIVE SHA}

if [[ $EUID -eq 0 ]]; then
  echo "Run as the application user; the script uses passwordless sudo for service configuration." >&2
  exit 1
fi
if [[ ! $sha =~ ^[0-9a-f]{40}$ ]]; then
  echo "Invalid Git SHA: $sha" >&2
  exit 1
fi
if [[ ! -f $archive ]]; then
  echo "Release archive not found." >&2
  exit 1
fi
sudo -n true
sudo test -f "$ENV_FILE"

app_user=$(id -un)
app_group=$(id -gn)
release="$RELEASES_DIR/$sha"
stage="$RELEASES_DIR/.staging-$sha-$$"
previous=""
switched=0
service_tmp=""

cleanup_stage() {
  if [[ -d $stage && $stage == "$RELEASES_DIR"/.staging-* ]]; then
    find "$stage" -mindepth 1 -delete
    rmdir "$stage"
  fi
}

rollback() {
  status=$?
  if [[ -n $service_tmp ]]; then rm -f "$service_tmp"; fi
  cleanup_stage || true
  if [[ $status -ne 0 && $switched -eq 1 && -n $previous && -d $previous ]]; then
    echo "Deployment failed; restoring previous release $(basename "$previous")." >&2
    ln -s "$previous" "$CURRENT_LINK.rollback"
    mv -Tf "$CURRENT_LINK.rollback" "$CURRENT_LINK"
    sudo systemctl restart casino-hackathon-backend.service || true
    sudo nginx -t && sudo systemctl reload nginx || true
  fi
  trap - EXIT
  exit "$status"
}
trap rollback EXIT

install -d -m 0755 "$APP_ROOT" "$RELEASES_DIR"
if [[ ! -d $release ]]; then
  install -d -m 0755 "$stage"
  tar -xzf "$archive" -C "$stage"
  test -f "$stage/Backend/app/main.py"
  test -f "$stage/Backend/requirements.txt"
  test -f "$stage/static/public/index.html"
  test -f "$stage/static/participant/index.html"
  test -f "$stage/static/admin/index.html"
  test "$(sed -n 's/^DEPLOYED_COMMIT=//p' "$stage/deploy.env")" = "$sha"
  chmod -R u=rwX,go=rX "$stage"
  mv "$stage" "$release"
fi
test -f "$release/Backend/app/main.py"
test -f "$release/static/public/index.html"
test -f "$release/static/participant/index.html"
test -f "$release/static/admin/index.html"
test "$(sed -n 's/^DEPLOYED_COMMIT=//p' "$release/deploy.env")" = "$sha"

if [[ ! -x $release/.venv/bin/python ]]; then
  python3 -m venv "$release/.venv"
fi
"$release/.venv/bin/python" -m pip install --upgrade pip
"$release/.venv/bin/pip" install -r "$release/Backend/requirements.txt"

service_tmp=$(mktemp)
sed -e "s/__APP_USER__/$app_user/g" -e "s/__APP_GROUP__/$app_group/g" \
  "$release/deploy/aws/casino-hackathon-backend.service" > "$service_tmp"
sudo install -o root -g root -m 0644 "$service_tmp" /etc/systemd/system/casino-hackathon-backend.service
sudo install -o root -g root -m 0644 "$release/deploy/aws/nginx.conf" /etc/nginx/conf.d/casino-hackathon.conf

if [[ -L $CURRENT_LINK ]]; then
  previous=$(readlink -f "$CURRENT_LINK")
fi
next_link="$CURRENT_LINK.next-$$"
ln -s "$release" "$next_link"
mv -Tf "$next_link" "$CURRENT_LINK"
switched=1

sudo systemctl daemon-reload
sudo systemctl enable casino-hackathon-backend.service nginx
sudo systemctl restart casino-hackathon-backend.service
sudo nginx -t
if sudo systemctl is-active --quiet nginx; then
  sudo systemctl reload nginx
else
  sudo systemctl start nginx
fi

for _ in {1..30}; do
  health=$(curl --silent --show-error http://127.0.0.1:8000/health || true)
  version=$(curl --silent --show-error http://127.0.0.1:8000/version || true)
  if [[ $health == '{"status":"ok"}' && $version == "{\"commit\":\"$sha\"}" ]]; then
    switched=0
    rm -f "$service_tmp"
    trap - EXIT
    echo "PASS deployed $sha"
    exit 0
  fi
  sleep 1
done

echo "Backend health/version verification failed." >&2
sudo systemctl --no-pager --full status casino-hackathon-backend.service >&2 || true
exit 1
