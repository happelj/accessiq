#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
gitleaks_image="${GITLEAKS_IMAGE:-zricethezav/gitleaks:v8.21.2}"

cd "${repo_root}"
scan_dir="$(mktemp -d)"

cleanup() {
  rm -rf "${scan_dir}"
}

trap cleanup EXIT

git ls-files -z --cached --others --exclude-standard | while IFS= read -r -d '' path
do
  case "${path}" in
    .mypy_cache/*|.pytest_cache/*|.ruff_cache/*|frontend/dist/*|frontend/node_modules/*|reports/*|sbom/*|accessiq-prometheus.yaml)
      continue
      ;;
  esac

  mkdir -p "${scan_dir}/$(dirname "${path}")"
  cp "${path}" "${scan_dir}/${path}"
done

cp .gitleaks.toml "${scan_dir}/.gitleaks.toml"

docker_scan_dir="${scan_dir}"

if command -v cygpath >/dev/null 2>&1; then
  docker_scan_dir="$(cygpath -w "${scan_dir}")"
fi

if command -v gitleaks >/dev/null 2>&1; then
  gitleaks detect \
    --no-git \
    --source "${scan_dir}" \
    --config "${scan_dir}/.gitleaks.toml" \
    --redact \
    --exit-code 1
  exit 0
fi

if command -v docker >/dev/null 2>&1; then
  MSYS_NO_PATHCONV=1 docker run --rm \
    -u 0 \
    -v "${docker_scan_dir}:/workspace" \
    -w /workspace \
    "${gitleaks_image}" detect \
      --no-git \
      --source /workspace \
      --config /workspace/.gitleaks.toml \
      --redact \
      --exit-code 1
  exit 0
fi

echo "Gitleaks or Docker is required for secret scanning." >&2
exit 127
