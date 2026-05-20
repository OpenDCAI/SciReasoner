#!/usr/bin/env bash
# Launch the SciReasoner MCP server inside the plugin's vendored venv.
# Used by Claude Code via .claude-plugin/mcp.json.
set -euo pipefail

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)}"
VENV_DIR="${PLUGIN_ROOT}/vendor/scireasoner-venv"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "scireasoner: venv not found at ${VENV_DIR}; run install.sh first." >&2
  exit 1
fi

# Activate venv and exec the MCP server entry point. stdio is the default.
# Forward env vars: OPENAI_API_KEY, OPENAI_BASE_URL, SCIREASONER_MODEL.
source "${VENV_DIR}/bin/activate"
exec scireasoner-mcp "$@"
