#!/usr/bin/env bash
# Build Chrome extension zip for distribution / GitHub Release.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT_DIR="${ROOT}/extension"
DIST_DIR="${ROOT}/dist"
MANIFEST="${EXT_DIR}/manifest.json"

if [[ ! -f "${MANIFEST}" ]]; then
  echo "error: manifest not found at ${MANIFEST}" >&2
  exit 1
fi

VERSION="$(python3 -c "import json; print(json.load(open('${MANIFEST}'))['version'])")"
NAME="browser-action-adapter"
OUT="${DIST_DIR}/${NAME}-${VERSION}.zip"

mkdir -p "${DIST_DIR}"

# Build from extension/ root so manifest.json is at archive root (required by Chrome).
(
  cd "${EXT_DIR}"
  zip -r "${OUT}" . \
    -x "*.DS_Store" \
    -x "*__MACOSX*" \
    -x "scripts/*" \
    -x ".git/*"
)

echo "Built: ${OUT}"
echo "Version: ${VERSION}"
echo ""
echo "Install (unpacked): chrome://extensions → Developer mode → Load unpacked → ${EXT_DIR}"
echo "Install (zip): unzip ${OUT} and load the extracted folder"
