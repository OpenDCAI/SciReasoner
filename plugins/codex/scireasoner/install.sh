#!/usr/bin/env bash
set -euo pipefail

# Install SciReasoner as a local Codex plugin.
#
# Codex's plugin model:
#   * marketplaces are directories registered in ~/.codex/config.toml under
#     [marketplaces.<name>] with `source = "<absolute path>"`.
#   * each marketplace contains:
#       <root>/.agents/plugins/marketplace.json
#       <root>/plugins/<plugin>/.codex-plugin/plugin.json
#   * plugins are enabled via [plugins."<plugin>@<marketplace>"] enabled = true
#
# This script lays the plugin out under ~/.codex/marketplaces/scireasoner/ and
# patches ~/.codex/config.toml.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PLUGIN_NAME="scireasoner"
MARKETPLACE_NAME="${SCIREASONER_CODEX_MARKETPLACE:-scireasoner}"
MARKETPLACE_ROOT="${HOME}/.codex/marketplaces/${MARKETPLACE_NAME}"
TARGET_DIR="${MARKETPLACE_ROOT}/plugins/${PLUGIN_NAME}"
MARKETPLACE_JSON="${MARKETPLACE_ROOT}/.agents/plugins/marketplace.json"
CODEX_CONFIG="${HOME}/.codex/config.toml"

REPO_ROOT=""
FORCE="false"
SKIP_DEPS="false"
PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
  cat <<EOF
Install SciReasoner as a Codex plugin.

Usage:
  ./install.sh [--repo-root PATH] [--force] [--skip-deps] [--python PATH]

Options:
  --repo-root PATH   SciReasoner repo root. Defaults to ../../.. from this dir.
  --force            Replace any existing install at ${MARKETPLACE_ROOT}.
  --skip-deps        Do not create venv or install Python dependencies.
  --python PATH      Python interpreter to use for venv creation.
  -h, --help         Show this help.

Override the marketplace name with SCIREASONER_CODEX_MARKETPLACE
(default: scireasoner).

Environment variables read by the running MCP server:
  OPENAI_API_KEY        # required
  OPENAI_BASE_URL       # optional
  SCIREASONER_MODEL     # optional, defaults to gemini-3.1-pro-preview
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root) REPO_ROOT="${2:-}"; shift 2 ;;
    --force)     FORCE="true"; shift ;;
    --skip-deps) SKIP_DEPS="true"; shift ;;
    --python)    PYTHON_BIN="${2:-}"; shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 1 ;;
  esac
done

# ---- Locate SciReasoner repo root ---------------------------------------
if [[ -z "${REPO_ROOT}" ]]; then
  REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd -P)"
fi
if [[ ! -f "${REPO_ROOT}/pyproject.toml" ]]; then
  echo "error: ${REPO_ROOT} doesn't look like the SciReasoner repo (no pyproject.toml)." >&2
  echo "       Pass --repo-root /path/to/SciReasoner explicitly." >&2
  exit 1
fi
echo "[scireasoner] repo root: ${REPO_ROOT}"

# ---- Sanity: do we have a Codex install? --------------------------------
if [[ ! -d "${HOME}/.codex" ]]; then
  echo "WARN: ${HOME}/.codex does not exist; will create it. If Codex isn't installed yet," >&2
  echo "      install Codex first, run it once, then re-run this script." >&2
  mkdir -p "${HOME}/.codex"
fi

# ---- Stage the marketplace + plugin -------------------------------------
mkdir -p "${MARKETPLACE_ROOT}/.agents/plugins" "${MARKETPLACE_ROOT}/plugins"

if [[ "${SCRIPT_DIR}" != "${TARGET_DIR}" ]]; then
  if [[ -e "${TARGET_DIR}" && "${FORCE}" != "true" ]]; then
    echo "Target already exists: ${TARGET_DIR}" >&2
    echo "Rerun with --force to replace it." >&2
    exit 1
  fi
  rm -rf "${TARGET_DIR}"
  mkdir -p "${TARGET_DIR}"
  rsync -a \
    --exclude ".DS_Store" \
    --exclude "__pycache__" \
    --exclude ".pytest_cache" \
    --exclude ".venv" \
    --exclude "vendor" \
    "${SCRIPT_DIR}/" "${TARGET_DIR}/"
fi
chmod +x "${TARGET_DIR}/install.sh" "${TARGET_DIR}/src/run_scireasoner_mcp.sh"

# ---- Set up venv + install scireasoner ----------------------------------
VENV_DIR="${TARGET_DIR}/vendor/scireasoner-venv"
if [[ "${SKIP_DEPS}" != "true" ]]; then
  if [[ -d "${VENV_DIR}" && "${FORCE}" == "true" ]]; then
    rm -rf "${VENV_DIR}"
  fi
  if [[ ! -d "${VENV_DIR}" ]]; then
    echo "[scireasoner] creating venv with ${PYTHON_BIN}..."
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  fi
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip wheel >/dev/null
  echo "[scireasoner] pip install -e ${REPO_ROOT}[mcp] into ${VENV_DIR}"
  "${VENV_DIR}/bin/python" -m pip install -e "${REPO_ROOT}[mcp]"
fi

# ---- Write marketplace catalogue ----------------------------------------
python3 - "${MARKETPLACE_JSON}" "${MARKETPLACE_NAME}" <<'PY'
import json, pathlib, sys

marketplace_path = pathlib.Path(sys.argv[1]).expanduser()
marketplace_name = sys.argv[2]

entry = {
    "name": "scireasoner",
    "source": {"source": "local", "path": "./plugins/scireasoner"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"},
    "category": "Productivity",
}

if marketplace_path.exists():
    payload = json.loads(marketplace_path.read_text(encoding="utf-8"))
else:
    payload = {"name": marketplace_name, "interface": {"displayName": "SciReasoner"}, "plugins": []}

payload.setdefault("name", marketplace_name)
payload.setdefault("interface", {}).setdefault("displayName", "SciReasoner")
plugins = payload.setdefault("plugins", [])
for i, plugin in enumerate(plugins):
    if isinstance(plugin, dict) and plugin.get("name") == entry["name"]:
        plugins[i] = entry
        break
else:
    plugins.append(entry)

marketplace_path.parent.mkdir(parents=True, exist_ok=True)
marketplace_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {marketplace_path}")
PY

# ---- Patch ~/.codex/config.toml -----------------------------------------
python3 - "${CODEX_CONFIG}" "${MARKETPLACE_NAME}" "${MARKETPLACE_ROOT}" <<'PY'
import pathlib, re, sys, datetime as dt

config_path = pathlib.Path(sys.argv[1]).expanduser()
mname, mroot = sys.argv[2], sys.argv[3]

config_path.parent.mkdir(parents=True, exist_ok=True)
text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def upsert_section(text, header, body):
    pattern = re.compile(r'(?ms)^' + re.escape(header) + r'\n(?:(?!^\[).*\n?)*')
    block = header + "\n" + body
    if not block.endswith("\n"):
        block += "\n"
    if pattern.search(text):
        text = pattern.sub(block, text, count=1)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        if text and not text.endswith("\n\n"):
            text += "\n"
        text += block
    return text

text = upsert_section(text,
    f'[marketplaces.{mname}]',
    f'last_updated = "{now}"\nsource_type = "local"\nsource = "{mroot}"\n')
text = upsert_section(text,
    f'[plugins."scireasoner@{mname}"]',
    'enabled = true\n')

config_path.write_text(text, encoding="utf-8")
print(f"Patched {config_path}")
PY

cat <<EOF

✅ SciReasoner installed for Codex.
   Marketplace name:   ${MARKETPLACE_NAME}
   Marketplace root:   ${MARKETPLACE_ROOT}
   Plugin source:      ${TARGET_DIR}
   Codex config:       ${CODEX_CONFIG}

Set credentials in your shell before launching Codex:
   export OPENAI_API_KEY=...
   export OPENAI_BASE_URL=...   # optional

Restart Codex (Cmd+Q then reopen). The plugin should appear in Codex's plugin
list and start automatically. Then in Codex you can ask:

   "Use SciReasoner to solve this physics problem [image]..."

Three MCP tools become available:
   scireasoner_solve     — end-to-end caption→reason→critic
   scireasoner_caption   — caption stage only
   scireasoner_reason    — reason stage only
EOF
