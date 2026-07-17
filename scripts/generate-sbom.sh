#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="${SBOM_OUTPUT_DIR:-sbom}"

cd "${repo_root}"
mkdir -p "${output_dir}"

if ! command -v cyclonedx-py >/dev/null 2>&1; then
  echo "cyclonedx-py is required. Install with: python -m pip install cyclonedx-bom" >&2
  exit 127
fi

python_sbom="${output_dir}/python-requirements.cdx.json"
frontend_sbom="${output_dir}/frontend-npm.cdx.json"

cyclonedx-py requirements requirements.txt \
  --output-format JSON \
  --output-file "${python_sbom}"

if ! command -v npx >/dev/null 2>&1; then
  echo "npx is required to generate the frontend npm SBOM." >&2
  exit 127
fi

(
  cd frontend
  npx --yes @cyclonedx/cyclonedx-npm \
    --output-format JSON \
    --output-file "../${frontend_sbom}"
)

echo "Generated SBOMs:"
echo "  ${python_sbom}"
echo "  ${frontend_sbom}"
