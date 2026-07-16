#!/usr/bin/env bash
set -euo pipefail

max_attempts="${PIP_AUDIT_MAX_ATTEMPTS:-3}"
retry_wait_seconds="${PIP_AUDIT_RETRY_WAIT_SECONDS:-20}"
timeout_seconds="${PIP_AUDIT_TIMEOUT_SECONDS:-60}"
cache_dir="${PIP_AUDIT_CACHE_DIR:-${RUNNER_TEMP:-/tmp}/pip-audit-cache}"
attempt=1

while true; do
  echo "Running Python dependency audit (attempt ${attempt}/${max_attempts})"

  if pip-audit \
    --requirement requirements.txt \
    --strict \
    --progress-spinner off \
    --timeout "${timeout_seconds}" \
    --cache-dir "${cache_dir}"; then
    exit 0
  else
    status=$?
  fi

  if [ "${attempt}" -ge "${max_attempts}" ]; then
    echo "pip-audit failed after ${max_attempts} attempts" >&2
    exit "${status}"
  fi

  echo "pip-audit failed with exit code ${status}; retrying in ${retry_wait_seconds}s"
  sleep "${retry_wait_seconds}"
  attempt=$((attempt + 1))
done
