#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${ACCESSIQ_BASE_URL:?ACCESSIQ_BASE_URL is required}"
BASE_URL="${BASE_URL%/}"
SMOKE_EMAIL="${ACCESSIQ_SMOKE_EMAIL:-alice@example.com}"
SMOKE_PASSWORD="${ACCESSIQ_SMOKE_PASSWORD:-Password123!}"

echo "Smoke test base URL: ${BASE_URL}"

curl --fail --silent --show-error "${BASE_URL}/health" >/dev/null
echo "health endpoint ok"

curl --fail --silent --show-error "${BASE_URL}/" >/dev/null
echo "frontend root ok"

curl --fail --silent --show-error "${BASE_URL}/openapi.json" >/dev/null
echo "OpenAPI endpoint ok"

LOGIN_RESPONSE="$(
  curl --fail --silent --show-error \
    --request POST \
    --header "Content-Type: application/json" \
    --data "{\"email\":\"${SMOKE_EMAIL}\",\"password\":\"${SMOKE_PASSWORD}\"}" \
    "${BASE_URL}/login"
)"

ACCESS_TOKEN="$(
  python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])' \
    <<<"${LOGIN_RESPONSE}"
)"

if [ -z "${ACCESS_TOKEN}" ]; then
  echo "login response did not include an access token" >&2
  exit 1
fi

echo "authentication endpoint ok"

curl --fail --silent --show-error \
  --header "Authorization: Bearer ${ACCESS_TOKEN}" \
  "${BASE_URL}/ai/providers" >/dev/null

echo "AI provider endpoint ok"
