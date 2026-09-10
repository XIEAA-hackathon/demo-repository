#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT=/opt/casino_hackathon
RELEASES_DIR="$APP_ROOT/releases"
CURRENT_LINK="$APP_ROOT/current"
ENV_FILE=/etc/casino-hackathon/backend.env
SERVICE_NAME=casino-hackathon-backend.service
NGINX_CONFIG=/etc/nginx/conf.d/casino-hackathon.conf
LOCK_FILE=/var/lock/casino-hackathon-deploy.lock
LOG_FILE=/var/log/casino-hackathon-deploy.log
RELEASE_LIMIT=6

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
deployment_stage="PUSH RECEIVED"
service_tmp=""
service_backup=""
nginx_backup=""
service_existed=0
nginx_existed=0
config_installed=0

sudo touch "$LOCK_FILE" "$LOG_FILE"
sudo chown "$app_user:$app_group" "$LOCK_FILE" "$LOG_FILE"
sudo chmod 0640 "$LOCK_FILE" "$LOG_FILE"
exec 9>"$LOCK_FILE"
if ! flock -w 300 9; then
  echo "Another deployment holds $LOCK_FILE; exiting safely." >&2
  exit 1
fi

log() {
  printf '%s sha=%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$sha" "$*" | tee -a "$LOG_FILE"
}

set_stage() {
  deployment_stage=$1
  log "$deployment_stage"
}

cleanup_stage() {
  if [[ -d $stage && $stage == "$RELEASES_DIR"/.staging-* ]]; then
    find "$stage" -mindepth 1 -delete
    rmdir "$stage"
  fi
}

cleanup_temporary_files() {
  [[ -z $service_tmp || ! -e $service_tmp ]] || rm -f "$service_tmp"
  [[ -z $service_backup || ! -e $service_backup ]] || rm -f "$service_backup"
  [[ -z $nginx_backup || ! -e $nginx_backup ]] || rm -f "$nginx_backup"
}

restore_service_configuration() {
  if [[ $config_installed -ne 1 ]]; then
    return
  fi
  if [[ $service_existed -eq 1 ]]; then
    sudo install -o root -g root -m 0644 "$service_backup" "/etc/systemd/system/$SERVICE_NAME"
  else
    sudo rm -f "/etc/systemd/system/$SERVICE_NAME"
  fi
  if [[ $nginx_existed -eq 1 ]]; then
    sudo install -o root -g root -m 0644 "$nginx_backup" "$NGINX_CONFIG"
  else
    sudo rm -f "$NGINX_CONFIG"
  fi
  sudo systemctl daemon-reload
}

rollback() {
  status=$?
  set +e
  cleanup_stage
  if [[ $status -ne 0 ]]; then
    log "FAILED AT: $deployment_stage"
    restore_service_configuration
    if [[ $switched -eq 1 && -n $previous && -d $previous ]]; then
      log "ROLLBACK START previous=$(basename "$previous")"
      rollback_link="$CURRENT_LINK.rollback-$$"
      ln -s "$previous" "$rollback_link"
      mv -Tf "$rollback_link" "$CURRENT_LINK"
      sudo systemctl restart "$SERVICE_NAME"
      if sudo nginx -t && sudo systemctl reload nginx \
        && [[ $(readlink -f "$CURRENT_LINK") == "$previous" ]] \
        && [[ $(curl --fail --silent --show-error http://127.0.0.1:8000/health) == '{"status":"ok"}' ]]; then
        log "ROLLBACK SUCCESS active=$(basename "$previous")"
      else
        log "ROLLBACK FAILED expected=$(basename "$previous")"
      fi
    fi
  fi
  cleanup_temporary_files
  trap - EXIT
  exit "$status"
}
trap rollback EXIT

prune_releases() {
  local current_resolved candidate name retained
  current_resolved=$(readlink -f "$CURRENT_LINK")
  retained=0
  declare -A keep=()
  keep["$current_resolved"]=1
  ((retained += 1))
  if [[ -n $previous && -d $previous && -z ${keep[$previous]+x} ]]; then
    keep["$previous"]=1
    ((retained += 1))
  fi
  while IFS= read -r candidate; do
    [[ -n $candidate ]] || continue
    if [[ $retained -lt $RELEASE_LIMIT && -z ${keep[$candidate]+x} ]]; then
      keep["$candidate"]=1
      ((retained += 1))
    fi
  done < <(find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
    | sort -nr | cut -d' ' -f2-)

  while IFS= read -r candidate; do
    [[ -n $candidate ]] || continue
    name=$(basename "$candidate")
    if [[ $name =~ ^[0-9a-f]{40}$ && -z ${keep[$candidate]+x} && $candidate != "$current_resolved" ]]; then
      log "RETENTION removing=$name"
      find "$candidate" -mindepth 1 -delete
      rmdir "$candidate"
    fi
  done < <(find "$RELEASES_DIR" -mindepth 1 -maxdepth 1 -type d -print)
}

log "PUSH RECEIVED"
set_stage "FETCHING"
install -d -m 0755 "$APP_ROOT" "$RELEASES_DIR"

set_stage "RELEASE CREATED"
if [[ ! -d $release ]]; then
  install -d -m 0755 "$stage"
  tar -xzf "$archive" -C "$stage"
  test -f "$stage/Backend/app/main.py"
  test -f "$stage/Backend/requirements.txt"
  test -f "$stage/static/index.html"
  test "$(sed -n 's/^DEPLOYED_COMMIT=//p' "$stage/deploy.env")" = "$sha"
  chmod -R u=rwX,go=rX "$stage"
  mv "$stage" "$release"
fi
test -f "$release/Backend/app/main.py"
test -f "$release/static/index.html"
test "$(sed -n 's/^DEPLOYED_COMMIT=//p' "$release/deploy.env")" = "$sha"
if find "$release" -type f \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print -quit | grep -q .; then
  echo "Release contains a database file; persistent data must stay outside releases." >&2
  exit 1
fi

set_stage "INSTALLING"
if [[ ! -x $release/.venv/bin/python ]]; then
  python3 -m venv "$release/.venv"
fi
"$release/.venv/bin/python" -m pip install --upgrade pip
"$release/.venv/bin/pip" install -r "$release/Backend/requirements.txt"

set_stage "BUILDING"
test -s "$release/static/index.html"

set_stage "VALIDATING"
sudo systemd-run --quiet --wait --pipe --collect \
  --uid="$app_user" --gid="$app_group" \
  -p "WorkingDirectory=$release/Backend" \
  -p "EnvironmentFile=$ENV_FILE" \
  "$release/.venv/bin/python" -c 'import app.main'

service_tmp=$(mktemp)
sed -e "s/__APP_USER__/$app_user/g" -e "s/__APP_GROUP__/$app_group/g" \
  "$release/deploy/aws/casino-hackathon-backend.service" > "$service_tmp"
service_backup=$(mktemp)
nginx_backup=$(mktemp)
if sudo test -f "/etc/systemd/system/$SERVICE_NAME"; then
  sudo cp "/etc/systemd/system/$SERVICE_NAME" "$service_backup"
  sudo chown "$app_user:$app_group" "$service_backup"
  service_existed=1
fi
if sudo test -f "$NGINX_CONFIG"; then
  sudo cp "$NGINX_CONFIG" "$nginx_backup"
  sudo chown "$app_user:$app_group" "$nginx_backup"
  nginx_existed=1
fi
sudo install -o root -g root -m 0644 "$service_tmp" "/etc/systemd/system/$SERVICE_NAME"
sudo install -o root -g root -m 0644 "$release/deploy/aws/nginx.conf" "$NGINX_CONFIG"
config_installed=1
sudo systemctl daemon-reload
sudo nginx -t

if [[ -L $CURRENT_LINK ]]; then
  previous=$(readlink -f "$CURRENT_LINK")
fi

set_stage "PROMOTING"
next_link="$CURRENT_LINK.next-$$"
ln -s "$release" "$next_link"
mv -Tf "$next_link" "$CURRENT_LINK"
switched=1
if [[ $(readlink -f "$CURRENT_LINK") != "$release" ]]; then
  echo "Atomic promotion verification failed." >&2
  exit 1
fi

set_stage "RESTARTING"
sudo systemctl enable "$SERVICE_NAME" nginx
sudo systemctl restart "$SERVICE_NAME"
if sudo systemctl is-active --quiet nginx; then
  sudo systemctl reload nginx
else
  sudo systemctl start nginx
fi

set_stage "HEALTH CHECK"
for _ in {1..30}; do
  internal_health=$(curl --silent --show-error http://127.0.0.1:8000/health || true)
  internal_version=$(curl --silent --show-error http://127.0.0.1:8000/version || true)
  proxy_health=$(curl --silent --show-error http://127.0.0.1/api/health || true)
  if [[ $internal_health == '{"status":"ok"}' \
    && $internal_version == "{\"commit\":\"$sha\"}" \
    && $proxy_health == '{"status":"ok"}' ]] \
    && curl --fail --silent --show-error http://127.0.0.1/ | grep -qi '<div id="root"></div>' \
    && curl --fail --silent --show-error http://127.0.0.1/admin/ | grep -qi '<div id="root"></div>' \
    && curl --fail --silent --show-error http://127.0.0.1/participant/ | grep -qi '<div id="root"></div>'; then
    switched=0
    set_stage "LIVE"
    log "active=$sha previous=$(basename "${previous:-none}")"
    prune_releases
    cleanup_temporary_files
    trap - EXIT
    exit 0
  fi
  sleep 1
done

echo "Backend or public health/version verification failed." >&2
sudo systemctl --no-pager --full status "$SERVICE_NAME" >&2 || true
exit 1
