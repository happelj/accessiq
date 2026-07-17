#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
report_dir="${TRIVY_REPORT_DIR:-reports/security}"
sbom_dir="${SBOM_OUTPUT_DIR:-sbom}"
severity="${TRIVY_SEVERITY:-CRITICAL,HIGH}"
trivy_image="${TRIVY_IMAGE:-aquasec/trivy:0.56.2}"
docker_repo_root="${repo_root}"

if command -v cygpath >/dev/null 2>&1; then
  docker_repo_root="$(cygpath -w "${repo_root}")"
fi

if [ "$#" -eq 0 ]; then
  echo "Usage: bash scripts/container-scan.sh <image> [image...]" >&2
  exit 2
fi

cd "${repo_root}"
mkdir -p "${report_dir}" "${sbom_dir}"

run_trivy() {
  if command -v trivy >/dev/null 2>&1; then
    trivy "$@"
    return
  fi

  if command -v docker >/dev/null 2>&1; then
    MSYS_NO_PATHCONV=1 docker run --rm \
      -v /var/run/docker.sock:/var/run/docker.sock \
      -v "${docker_repo_root}:/workspace" \
      -w /workspace \
      "${trivy_image}" "$@"
    return
  fi

  echo "Trivy or Docker is required for container scanning." >&2
  exit 127
}

scan_status=0

for image in "$@"; do
  safe_name="$(printf "%s" "${image}" | tr '/:@' '___')"
  report_path="${report_dir}/${safe_name}.trivy.txt"
  image_sbom_path="${sbom_dir}/${safe_name}.image.cdx.json"

  echo "Scanning ${image}"
  if ! run_trivy image \
    --ignore-unfixed \
    --severity "${severity}" \
    --exit-code 1 \
    --format table \
    --output "${report_path}" \
    "${image}"; then
    scan_status=1
  fi

  run_trivy image \
    --format cyclonedx \
    --output "${image_sbom_path}" \
    "${image}"

  echo "  Report: ${report_path}"
  echo "  Image SBOM: ${image_sbom_path}"
done

exit "${scan_status}"
