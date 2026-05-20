# SciReasoner — Codex Plugin

> Multimodal physics problem solving for OpenAI Codex. 1st place ICML 2025 SeePhys.

## Quick install

```bash
git clone https://github.com/OpenDCAI/SciReasoner.git
cd SciReasoner/plugins/codex/scireasoner
bash install.sh
```

This:
1. Stages the plugin under `~/.codex/marketplaces/scireasoner/plugins/scireasoner/`
2. Creates a Python venv at `~/.codex/marketplaces/scireasoner/plugins/scireasoner/vendor/scireasoner-venv/`
3. Installs the `scireasoner` package (with `[mcp]` extra) inside the venv
4. Writes `~/.codex/marketplaces/scireasoner/.agents/plugins/marketplace.json`
5. Patches `~/.codex/config.toml` to register the marketplace and enable the plugin

Restart Codex (Cmd+Q, reopen) afterwards. The plugin auto-starts.

## Credentials

Before launching Codex, set:

```bash
export OPENAI_API_KEY=<your-key>
export OPENAI_BASE_URL=<endpoint>      # optional
export SCIREASONER_MODEL=<model>       # optional, default: gemini-3.1-pro-preview
```

## What you get

Three MCP tools available in Codex:

| Tool | Description |
|---|---|
| `scireasoner_solve` | End-to-end caption→reason→critic on one physics problem. |
| `scireasoner_caption` | Caption stage only — figure → structured text. |
| `scireasoner_reason` | Reason stage only. |

Plus the auto-trigger skill `solve-physics-problem`.

## Usage

```
> Use SciReasoner to solve this physics problem:
  [image of an RC circuit]
```

```
> Use SciReasoner with k_samples=3 to solve:
  A 2 kg block slides from rest down a 30° incline...
```

## Uninstall

```bash
rm -rf ~/.codex/marketplaces/scireasoner
```

Then remove these blocks from `~/.codex/config.toml`:
```toml
[marketplaces.scireasoner]
...
[plugins."scireasoner@scireasoner"]
enabled = true
```

## Internals

Same MCP server as the Claude Code plugin variant — both wrap the
`scireasoner` Python package, which is itself a thin shell over the live
SeePhys Pro competition codebase. Updates flow through:
`git pull && bash install.sh --force`.
