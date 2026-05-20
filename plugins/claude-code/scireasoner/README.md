# SciReasoner — Claude Code Plugin

> Multimodal physics problem solving for Claude Code. 1st place ICML 2025 SeePhys.

## Quick install

```bash
git clone https://github.com/OpenDCAI/SciReasoner.git
cd SciReasoner/plugins/claude-code/scireasoner
bash install.sh
```

Restart Claude Code afterwards. Confirm:

```bash
claude plugin list           # should include scireasoner@scireasoner
claude mcp list              # should show plugin:scireasoner:scireasoner ✓ Connected
```

## Credentials

Set these in your shell before launching Claude Code:

```bash
export OPENAI_API_KEY=<your-key>
export OPENAI_BASE_URL=<endpoint>      # optional, e.g. OpenAI-compatible proxy
export SCIREASONER_MODEL=<model>       # optional, defaults to gemini-3.1-pro-preview
```

The model name should resolve at your endpoint. Default `gemini-3.1-pro-preview` works on OpenRouter and most aggregator proxies.

## What you get

Three MCP tools available in Claude Code:

| Tool | Description |
|---|---|
| `scireasoner_solve` | End-to-end caption→reason→critic on one physics problem. Returns `{answer, reasoning, caption}`. |
| `scireasoner_caption` | Caption stage only — turn a figure into structured text. |
| `scireasoner_reason` | Reason stage only — derive from problem (+ optional caption). |

Plus one auto-trigger skill:

- **`solve-physics-problem`** — fires when the user asks Claude to solve a physics problem, especially when a figure is attached.

## Usage examples

**Text-only**:
```
> Use scireasoner_solve to find the speed at the bottom: a 2 kg block slides
  from rest down a 30° incline of length 5 m, μ = √3/10, take g = 10.
```

**With a figure**:
```
> [user pastes image of an RC circuit problem]
> Please solve this for me.
```

Claude Code's `solve-physics-problem` skill will auto-trigger and call
`scireasoner_solve(problem="...", image_path="<the image>")`.

**Higher accuracy via self-consistency** (3× cost on reason):
```
> Solve this with k_samples=3 self-consistency voting.
```

## Uninstall

```bash
claude plugin uninstall scireasoner@scireasoner
claude plugin marketplace remove scireasoner
rm -rf vendor/scireasoner-venv
```

## Troubleshooting

- **`claude mcp list` shows ✗ Failed**: re-run `bash install.sh --force`. Common cause is venv missing or pip not finding the package.
- **`AuthenticationError 401`**: your `$OPENAI_API_KEY` is missing or wrong, or the endpoint at `$OPENAI_BASE_URL` doesn't accept it.
- **Tool calls hang**: physics problems with thinking-heavy models (Gemini 3.1 Pro) can take 30-90 s end-to-end. Be patient.

## Internals

- The plugin's MCP server is a thin wrapper over the `scireasoner` Python package (in the parent repo's `scireasoner/` directory).
- `scireasoner` is itself a thin shell over the active competition codebase at `seephys_pro_codabench/scripts/run_v2.py`. So when the SciReasoner authors push prompt or strategy improvements during the live SeePhys Pro competition, you get them automatically — just `git pull && bash install.sh --force`.

See the top-level `README.md` of the SciReasoner repository for the paper, certificate, and benchmark results.
