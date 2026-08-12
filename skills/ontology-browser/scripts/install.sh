#!/usr/bin/env bash
# Install pip deps + copy skill into OpenClaw / Hermes skills directory.
set -euo pipefail

TARGET="${1:-auto}"
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SKILL_SRC="${SKILL_SRC:-$REPO_ROOT/skills/ontology-browser}"

if [[ ! -f "$SKILL_SRC/SKILL.md" ]]; then
  # Installed wheel: skill bundled next to package
  SKILL_SRC="$(python3 -c "import ontology_platform.browser_adapter.skill_paths as s; print(s.skill_dir())" 2>/dev/null || true)"
fi
if [[ -z "${SKILL_SRC:-}" || ! -f "$SKILL_SRC/SKILL.md" ]]; then
  echo "error: cannot locate skills/ontology-browser/SKILL.md" >&2
  exit 1
fi

echo "Installing ontology-agent-platform[browser] ..."
pip install -e "${REPO_ROOT}[browser]" 2>/dev/null || pip install "ontology-agent-platform[browser]" 2>/dev/null || {
  pip install -e "${REPO_ROOT}[browser]"
}

install_to() {
  local dest="$1"
  mkdir -p "$dest"
  rm -rf "$dest"
  cp -a "$SKILL_SRC/." "$dest/"
  echo "Skill installed → $dest"
}

case "$TARGET" in
  openclaw)
    install_to "${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/skills}/ontology-browser"
    ;;
  hermes)
    install_to "${HERMES_SKILLS_DIR:-$HOME/.hermes/skills}/ontology-browser"
    ;;
  auto)
    if [[ -d "$HOME/.openclaw" ]]; then
      install_to "$HOME/.openclaw/skills/ontology-browser"
    elif [[ -d "$HOME/.hermes" ]]; then
      install_to "$HOME/.hermes/skills/ontology-browser"
    else
      install_to "$HOME/.local/share/ontology-browser/skill"
      echo "Tip: set OPENCLAW_SKILLS_DIR or HERMES_SKILLS_DIR, or run: ontology-browser-client install-skill --target openclaw"
    fi
    ;;
  *)
    install_to "$TARGET"
    ;;
esac

echo "Starting local bridge if needed ..."
ontology-browser-client ensure-bridge
ontology-browser-client health
echo "Done. Configure Chrome extension Bridge URL → ${BROWSER_BRIDGE_URL:-http://127.0.0.1:9920}"
