#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT=/home/ec2-user/demo-repository
BACKEND_ROOT="$REPO_ROOT/Backend"
VENV_ROOT="$BACKEND_ROOT/venv"
STATIC_ROOT=/opt/casino_hackathon/current/static
STAGING_ROOT=/home/ec2-user/deploy-staging
BACKUP_ROOT=/opt/casino_hackathon/main1-backups
STATE_ROOT=/home/ec2-user/deploy-state
STATE_FILE="$STATE_ROOT/main1-deployed-sha"
# Shared with deploy-release.sh so the main and main1 pipelines cannot mutate
# the same service/static tree concurrently.
LOCK_FILE=/var/lock/casino-hackathon-deploy.lock
LOG_FILE=/var/log/casino-hackathon-deploy.log
SERVICE_NAME=casino-backend.service
BACKUP_LIMIT=5

deploy_sha=${1:?Usage: deploy-main1-remote.sh SHA FRONTEND_ARCHIVE}
frontend_archive=${2:?Usage: deploy-main1-remote.sh SHA FRONTEND_ARCHIVE}

if [[ ! $deploy_sha =~ ^[0-9a-f]{40}$ ]]; then
  echo "Invalid deployment SHA." >&2
  exit 1
fi
if [[ $(id -un) != ec2-user ]]; then
  echo "This deployment must run as ec2-user." >&2
  exit 1
fi
if [[ ! -f $frontend_archive || $frontend_archive != "$STAGING_ROOT"/incoming-"$deploy_sha"/* ]]; then
  echo "Frontend archive is missing or outside the expected staging directory." >&2
  exit 1
fi

install -d -m 0700 "$STAGING_ROOT" "$STATE_ROOT"
install -d -m 0750 "$BACKUP_ROOT"
if [[ ! -w $LOG_FILE ]]; then
  LOG_FILE="$STAGING_ROOT/main1-deploy.log"
  touch "$LOG_FILE"
fi
exec 9>"$LOCK_FILE"
if ! flock -w 900 9; then
  echo "Another main1 deployment is still running." >&2
  exit 1
fi

run_root="$STAGING_ROOT/run-$deploy_sha-$$"
source_root="$run_root/source"
frontend_root="$run_root/frontend"
next_static="$run_root/static"
backup=""
previous_sha=""
backend_changed=0
frontend_changed=0
stage="INITIALIZING"

log() {
  printf '%s pipeline=main1 commit=%s stage=%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$deploy_sha" "$stage" "$*" | tee -a "$LOG_FILE"
}

safe_remove_tree() {
  local target=$1 expected_root=$2
  [[ -n $target && -d $target && $target == "$expected_root"/* ]] || return 1
  find "$target" -mindepth 1 -delete
  rmdir "$target"
}

restore_backend() {
  [[ -n $backup && -d $backup/backend ]] || return 0
  log "Restoring previous Backend source"
  rsync -a --delete \
    --exclude '.env' --exclude 'venv/' --exclude '.venv/' \
    --exclude '*.db' --exclude '*.sqlite' --exclude '*.sqlite3' \
    --exclude '*.log' --exclude '__pycache__/' --exclude '.pytest_cache/' \
    "$backup/backend/" "$BACKEND_ROOT/"
  if [[ -f $backup/backend/requirements.txt ]]; then
    "$VENV_ROOT/bin/python" -m pip install --disable-pip-version-check -r "$backup/backend/requirements.txt" || true
  fi
  sudo -n /usr/bin/systemctl restart "$SERVICE_NAME" || true
}

restore_frontend() {
  [[ -n $backup && -d $backup/static ]] || return 0
  log "Restoring previous static tree"
  rsync -a --delete "$backup/static/" "$STATIC_ROOT/"
  sudo -n /usr/sbin/nginx -t || true
  sudo -n /usr/bin/systemctl reload nginx.service || true
}

finish() {
  local status=$?
  set +e
  if [[ $status -ne 0 ]]; then
    log "FAILED"
    if [[ $frontend_changed -eq 1 ]]; then restore_frontend; fi
    if [[ $backend_changed -eq 1 ]]; then restore_backend; fi
    sudo -n /usr/bin/journalctl --no-pager -u "$SERVICE_NAME" -n 80 >&2 || true
  fi
  if [[ -d $run_root && $run_root == "$STAGING_ROOT"/run-* ]]; then
    safe_remove_tree "$run_root" "$STAGING_ROOT" || true
  fi
  incoming_dir=$(dirname "$frontend_archive")
  if [[ -d $incoming_dir && $incoming_dir == "$STAGING_ROOT"/incoming-"$deploy_sha" ]]; then
    safe_remove_tree "$incoming_dir" "$STAGING_ROOT" || true
  fi
  trap - EXIT
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT TERM

stage="PREFLIGHT"
log "Checking production paths and tools"
test -d "$REPO_ROOT/.git"
test -d "$BACKEND_ROOT"
test -x "$VENV_ROOT/bin/python"
test -d "$STATIC_ROOT/public"
test -d "$STATIC_ROOT/admin"
test -d "$STATIC_ROOT/participant"
test -w "$STATIC_ROOT"
command -v rsync >/dev/null
command -v curl >/dev/null
sudo -n /usr/sbin/nginx -t

stage="FETCHING"
log "Fetching origin/main1"
git -C "$REPO_ROOT" fetch --no-tags origin main1
remote_sha=$(git -C "$REPO_ROOT" rev-parse origin/main1)
if [[ $remote_sha != "$deploy_sha" ]]; then
  echo "origin/main1 is $remote_sha, not requested commit $deploy_sha." >&2
  exit 1
fi

if [[ -f $STATE_FILE ]]; then
  previous_sha=$(tr -d '[:space:]' < "$STATE_FILE")
fi
if [[ ! $previous_sha =~ ^[0-9a-f]{40}$ ]] || ! git -C "$REPO_ROOT" cat-file -e "$previous_sha^{commit}" 2>/dev/null; then
  previous_sha=$(git -C "$REPO_ROOT" rev-parse HEAD)
fi
if ! git -C "$REPO_ROOT" diff --quiet "$previous_sha" -- Backend; then
  echo "Backend contains tracked changes relative to the last deployed commit; refusing to overwrite them." >&2
  git -C "$REPO_ROOT" diff --name-status "$previous_sha" -- Backend >&2
  exit 1
fi

stage="STAGING"
log "Preparing isolated Backend and frontend trees"
install -d -m 0700 "$source_root" "$frontend_root" "$next_static/public" "$next_static/admin" "$next_static/participant"
git -C "$REPO_ROOT" archive "$deploy_sha" Backend | tar -x -C "$source_root"
tar -xzf "$frontend_archive" -C "$frontend_root"
test -s "$source_root/Backend/app/main.py"
test -s "$source_root/Backend/requirements.txt"
test -s "$frontend_root/index.html"
test -d "$frontend_root/assets"
if find "$frontend_root" -type l -print -quit | grep -q .; then
  echo "Frontend archive unexpectedly contains symbolic links." >&2
  exit 1
fi
if find "$source_root/Backend" -type f \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' -o -name '.env' \) -print -quit | grep -q .; then
  echo "Backend release contains persistent data or an environment file." >&2
  exit 1
fi
rsync -a "$frontend_root/" "$next_static/public/"
install -m 0644 "$frontend_root/index.html" "$next_static/admin/index.html"
install -m 0644 "$frontend_root/index.html" "$next_static/participant/index.html"

stage="BACKUP"
backup="$BACKUP_ROOT/$(date -u +'%Y%m%dT%H%M%SZ')-${previous_sha:0:12}"
log "Saving rollback snapshot at $backup"
install -d -m 0750 "$backup/backend" "$backup/static"
rsync -a \
  --exclude '.env' --exclude 'venv/' --exclude '.venv/' \
  --exclude '*.db' --exclude '*.sqlite' --exclude '*.sqlite3' \
  --exclude '*.log' --exclude '__pycache__/' --exclude '.pytest_cache/' \
  "$BACKEND_ROOT/" "$backup/backend/"
rsync -a "$STATIC_ROOT/" "$backup/static/"
printf '%s\n' "$previous_sha" > "$backup/deployed-sha"

stage="BACKEND DEPENDENCIES"
backend_changed=1
log "Installing Backend requirements with $($VENV_ROOT/bin/python --version 2>&1)"
"$VENV_ROOT/bin/python" -m pip install --disable-pip-version-check -r "$source_root/Backend/requirements.txt"

stage="BACKEND VALIDATION"
log "Importing app.main:app before promotion"
(
  cd "$source_root/Backend"
  DATABASE_URL="sqlite:////home/ec2-user/demo-repository/Backend/casino_hackathon.db" \
    "$VENV_ROOT/bin/python" -c 'from app.main import app; assert app is not None'
)

stage="BACKEND PROMOTION"
log "Promoting tested Backend source while preserving venv, environment, and SQLite data"
rsync -a --delete \
  --exclude '.env' --exclude 'venv/' --exclude '.venv/' \
  --exclude '*.db' --exclude '*.sqlite' --exclude '*.sqlite3' \
  --exclude '*.log' --exclude '__pycache__/' --exclude '.pytest_cache/' \
  "$source_root/Backend/" "$BACKEND_ROOT/"

stage="BACKEND RESTART"
log "Restarting $SERVICE_NAME"
sudo -n /usr/bin/systemctl restart "$SERVICE_NAME"
for _ in {1..30}; do
  if /usr/bin/systemctl is-active --quiet "$SERVICE_NAME" \
    && [[ $(curl --silent --show-error http://127.0.0.1:8000/health || true) == '{"status":"ok"}' ]]; then
    break
  fi
  sleep 1
done
if ! /usr/bin/systemctl is-active --quiet "$SERVICE_NAME" \
  || [[ $(curl --silent --show-error http://127.0.0.1:8000/health || true) != '{"status":"ok"}' ]]; then
  echo "$SERVICE_NAME failed its local health check." >&2
  exit 1
fi
log "Backend service is active and healthy"

stage="FRONTEND PROMOTION"
frontend_changed=1
log "Promoting umbrella build into public, admin, and participant static roots"
rsync -a --delete --delay-updates "$next_static/public/" "$STATIC_ROOT/public/"
rsync -a --delete --delay-updates "$next_static/admin/" "$STATIC_ROOT/admin/"
rsync -a --delete --delay-updates "$next_static/participant/" "$STATIC_ROOT/participant/"

stage="NGINX VALIDATION"
sudo -n /usr/sbin/nginx -t
sudo -n /usr/bin/systemctl reload nginx.service
log "Nginx configuration validated and reloaded"

stage="HEALTH CHECK"
test "$(curl --fail --silent --show-error http://127.0.0.1:8000/health)" = '{"status":"ok"}'
test "$(curl --fail --silent --show-error http://127.0.0.1/api/health)" = '{"status":"ok"}'
for path in / /admin/ /participant/ /leaderboard; do
  curl --fail --silent --show-error "http://127.0.0.1$path" | grep -qi '<div id="root"></div>'
done

stage="LIVE"
printf '%s\n' "$deploy_sha" > "$STATE_FILE"
backend_changed=0
frontend_changed=0
log "Deployment completed successfully"

mapfile -t expired_backups < <(
  find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
    | sort -nr | tail -n +$((BACKUP_LIMIT + 1)) | cut -d' ' -f2-
)
for candidate in "${expired_backups[@]}"; do
  [[ -n $candidate && $candidate == "$BACKUP_ROOT"/* && -d $candidate ]] || continue
  log "Pruning old rollback snapshot $(basename "$candidate")"
  safe_remove_tree "$candidate" "$BACKUP_ROOT"
done
