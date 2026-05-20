#!/usr/bin/env bash
# Install SciReasoner as a Claude Code plugin via the local marketplace.
#
# What this does:
#   1. Locate the SciReasoner repo root (parent of this plugin dir).
#   2. Create a Python venv under vendor/scireasoner-venv/.
#   3. pip install the scireasoner package (with the [mcp] extra) into it.
#   4. Run `claude plugin marketplace add` and `claude plugin install` so the
#      plugin appears after the next Claude Code restart.
#
# Usage:
#   ./install.sh [--repo-root /path/to/SciReasoner] [--force] [--skip-deps] [--python python3]
#
# After running, restart Claude Code and confirm:
#   claude plugin list           # should include scireasoner@scireasoner
#   claude mcp list              # should show plugin:scireasoner:scireasoner ✓ Connected
#
# Environment variables read by the running MCP server:
#   OPENAI_API_KEY        # required
#   OPENAI_BASE_URL       # optional, OpenAI-compatible proxy
#   SCIREASONER_MODEL     # optional, defaults to gemini-3.1-pro-preview
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PLUGIN_NAME="scireasoner"
MARKETPLACE_NAME="scireasoner"
REPO_ROOT=""
FORCE="false"
SKIP_DEPS="false"
PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
  cat <<'EOF'
Install SciReasoner as a Claude Code plugin.

Usage:
  ./install.sh [--repo-root PATH] [--force] [--skip-deps] [--python PATH]

Options:
  --repo-root PATH   SciReasoner repo root (defaults to ../../.. from this dir).
  --force            Replace any previous local install.
  --skip-deps        Do not create venv or install Python dependencies.
                     You must already have `scireasoner-mcp` on PATH.
  --python PATH      Python interpreter to use for venv creation.
  -h, --help         Show this help.

Requirements:
  - Python 3.10+
  - `claude` CLI (https://docs.claude.com/claude-code)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    --force) FORCE="true"; shift ;;
    --skip-deps) SKIP_DEPS="true"; shift ;;
    --python) PYTHON_BIN="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown flag: $1" >&2; usage; exit 2 ;;
  esac
done

# ---- Locate SciReasoner repo root --------------------------------------
if [[ -z "${REPO_ROOT}" ]]; then
  REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd -P)"
fi
if [[ ! -f "${REPO_ROOT}/pyproject.toml" ]]; then
  echo "error: ${REPO_ROOT} doesn't look like the SciReasoner repo (no pyproject.toml)." >&2
  echo "       Pass --repo-root /path/to/SciReasoner explicitly." >&2
  exit 1
fi
echo "[scireasoner] repo root: ${REPO_ROOT}"

# ---- Set up venv + install scireasoner ---------------------------------
VENV_DIR="${SCRIPT_DIR}/vendor/scireasoner-venv"
if [[ "${SKIP_DEPS}" != "true" ]]; then
  if [[ -d "${VENV_DIR}" && "${FORCE}" == "true" ]]; then
    echo "[scireasoner] removing existing venv..."
    rm -rf "${VENV_DIR}"
  fi
  if [[ ! -d "${VENV_DIR}" ]]; then
    echo "[scireasoner] creating venv with ${PYTHON_BIN}..."
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  fi
  # shellcheck source=/dev/null
  source "${VENV_DIR}/bin/activate"
  pip install --upgrade pip wheel >/dev/null
  echo "[scireasoner] pip install -e ${REPO_ROOT}[mcp] ..."
  pip install -e "${REPO_ROOT}[mcp]"
  deactivate
fi

# ---- Make MCP launcher executable --------------------------------------
chmod +x "${SCRIPT_DIR}/src/run_scireasoner_mcp.sh"

# ---- Register with Claude Code -----------------------------------------
if ! command -v claude >/dev/null 2>&1; then
  echo "[scireasoner] WARNING: \`claude\` CLI not found. Skipping plugin registration." >&2
  echo "             Install it from https://docs.claude.com/claude-code and re-run." >&2
  exit 0
fi

if [[ "${FORCE}" == "true" ]]; then
  claude plugin marketplace remove "${MARKETPLACE_NAME}" 2>/dev/null || true
fi

echo "[scireasoner] adding marketplace ${MARKETPLACE_NAME} → ${SCRIPT_DIR}"
claude plugin marketplace add "${SCRIPT_DIR}" || true

echo "[scireasoner] installing plugin ${PLUGIN_NAME}@${MARKETPLACE_NAME}"
claude plugin install "${PLUGIN_NAME}@${MARKETPLACE_NAME}"

cat <<EOF

✅ SciReasoner installed as a Claude Code plugin.

Restart Claude Code, then verify:
    claude plugin list
    claude mcp list      # should show plugin:scireasoner:scireasoner ✓ Connected

Set credentials in your shell before using:
    export OPENAI_API_KEY=...
    export OPENAI_BASE_URL=...   # optional, e.g. an OpenAI-compatible proxy

In Claude Code, the plugin exposes three tools:
    scireasoner_solve     — end-to-end caption→reason→critic on a physics problem
    scireasoner_caption   — only the caption stage (image → structured text)
    scireasoner_reason    — reason stage given problem (+ optional caption)

Skill 'solve-physics-problem' will auto-trigger when the user asks Claude to
solve a physics problem with a figure.
EOF
