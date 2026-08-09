#!/usr/bin/env bash
set -Eeuo pipefail
BASE_URL=${BASE_URL:-http://127.0.0.1}
EXPECTED_SHA=${EXPECTED_SHA:-}

for path in / /participant/ /participant/dashboard /admin/; do
  curl --fail --silent --show-error "$BASE_URL$path" | grep -qi '<div id="root"></div>'
  echo "PASS $path"
done
test "$(curl --fail --silent --show-error "$BASE_URL/api/health")" = '{"status":"ok"}'
echo 'PASS /api/health'
if [[ -n $EXPECTED_SHA ]]; then
  test "$(curl --fail --silent --show-error "$BASE_URL/api/version")" = "{\"commit\":\"$EXPECTED_SHA\"}"
  echo "PASS /api/version $EXPECTED_SHA"
fi
