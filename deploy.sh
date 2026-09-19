#!/usr/bin/env bash
set -euo pipefail

# --------------------------------------------------
# CONFIG
# --------------------------------------------------

BRANCH="main1"
REMOTE="origin"

SSH_KEY="/c/Users/ADMIN/Documents/bidtobuild.pem"
SERVER="ubuntu@100.24.242.28"

REMOTE_REPO="/home/ubuntu/demo-repository"
FRONTEND_DIR="frontend-website"
WEB_ROOT="/var/www/bidtobuild"

SERVICE="casino-backend.service"

# Commit message:
# ./deploy.sh "fixed wildcard final choice"
COMMIT_MESSAGE="${1:-Deploy update}"

# --------------------------------------------------
# LOCAL
# --------------------------------------------------

echo "========================================"
echo "  BidToBuild Deployment"
echo "========================================"

echo
echo "[1/7] Checking current branch..."

CURRENT_BRANCH=$(git branch --show-current)

if [[ "$CURRENT_BRANCH" != "$BRANCH" ]]; then
    echo "ERROR: You are on '$CURRENT_BRANCH'."
    echo "Expected branch: '$BRANCH'"
    exit 1
fi

echo "Branch: $CURRENT_BRANCH"

echo
echo "[2/7] Adding changes..."

git add .

if git diff --cached --quiet; then
    echo "No new staged changes to commit."
else
    echo
    echo "[3/7] Creating commit..."
    git commit -m "$COMMIT_MESSAGE"
fi

echo
echo "[4/7] Pushing to GitHub..."

git push "$REMOTE" "$BRANCH"

# --------------------------------------------------
# SERVER
# --------------------------------------------------

echo
echo "[5/7] Connecting to production server..."

ssh \
    -o IdentitiesOnly=yes \
    -i "$SSH_KEY" \
    "$SERVER" << 'REMOTE_SCRIPT'

set -euo pipefail

REPO="/home/ubuntu/demo-repository"
BRANCH="main1"
FRONTEND_DIR="frontend-website"
WEB_ROOT="/var/www/bidtobuild"
SERVICE="casino-backend.service"

echo
echo "========================================"
echo "  Production Deployment"
echo "========================================"

echo
echo "[SERVER 1/5] Updating repository..."

cd "$REPO"

git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo
echo "Current commit:"
git log -1 --oneline

echo
echo "[SERVER 2/5] Building frontend..."

cd "$REPO/$FRONTEND_DIR"

npm run build

echo
echo "[SERVER 3/5] Restarting backend..."

sudo systemctl restart "$SERVICE"

echo
echo "[SERVER 4/5] Deploying frontend..."

sudo rm -rf "$WEB_ROOT"/*
sudo cp -r dist/* "$WEB_ROOT"/

echo
echo "[SERVER 5/5] Checking backend service..."

if sudo systemctl is-active --quiet "$SERVICE"; then
    echo "Backend service: ACTIVE"
else
    echo "ERROR: Backend service failed to start."
    sudo systemctl status "$SERVICE" --no-pager
    exit 1
fi

echo
echo "Backend service status:"
sudo systemctl status "$SERVICE" --no-pager --lines=10

echo
echo "========================================"
echo "  Deployment complete"
echo "========================================"

REMOTE_SCRIPT