<div align="center">

# SciReasoner

**Multimodal physics problem solving — caption → reason → critic.**

[![Paper](https://img.shields.io/badge/arXiv-2509.06079-b31b1b.svg)](https://arxiv.org/abs/2509.06079)
[![License](https://img.shields.io/badge/License-GPL_3.0-blue.svg)](LICENSE)
[![ICML 2025](https://img.shields.io/badge/ICML_2025-1st_Place-gold.svg)](https://sites.google.com/view/ai4mathworkshopicml2025)
[![SeePhys Pro](https://img.shields.io/badge/SeePhys_Pro-Codabench_16010-success.svg)](https://www.codabench.org/competitions/16010/)

🥇 **1st Place — ICML 2025 AI for Math Workshop, Track 2: Physics Reasoning with Diagrams and Expressions**

<img src="assets/certificate.jpg" alt="ICML 2025 AI4Math First Place Certificate" width="640"/>

</div>

---

## What it does

A three-stage pipeline that solves multimodal physics problems by **describing the figure**, **deriving an answer**, and then **critiquing and refining** that answer:

```
Caption (image → text) → Reason (solve) → Critic (review & correct)
```

Default model: Gemini-3.1-Pro on any OpenAI-compatible endpoint.

## Use it

```bash
git clone https://github.com/OpenDCAI/SciReasoner.git
cd SciReasoner
pip install -e .

export OPENAI_API_KEY=<your-key>
export OPENAI_BASE_URL=<endpoint>          # optional, OpenAI-compatible proxy
```

**As a CLI**:

```bash
scireasoner solve --problem "A 2 kg block slides from rest down a 30° incline of length 5 m, μ=√3/10, g=10. Find the speed at the bottom."
scireasoner solve --problem "Find I(t)." --image circuit.png
```

**As a Python library**:

```python
from scireasoner import solve
res = solve(problem="...", image="figure.png")
print(res.answer, res.reasoning)
```

**Inside Claude Code** (one-click install):

```bash
cd plugins/claude-code/scireasoner && bash install.sh
```

**Inside Codex** (one-click install):

```bash
cd plugins/codex/scireasoner && bash install.sh
```

Both plugins expose three MCP tools — `scireasoner_solve`, `scireasoner_caption`, `scireasoner_reason` — and auto-trigger a `solve-physics-problem` skill when the user asks for help with a physics problem.

## Reproduce SeePhys Pro 2026

```bash
pip install -e ".[batch]"
hf download Kun-Xiang/SeePhysPro --repo-type dataset --local-dir ./data/SeePhysPro

python seephys_pro_codabench/scripts/run_v2.py \
    --run v2_pub830 --split testmini --levels level1 level2 level3 level4 level5 \
    --caption-model gemini-3.1-pro-preview --reason-model gemini-3.1-pro-preview \
    --critic-model gemini-3.1-pro-preview --use-critic --k-samples 1 --workers 50

python seephys_pro_codabench/scripts/audit_fix.py --run output/v2_pub830
# Upload submission_audited.zip to https://www.codabench.org/competitions/16010/
```

Per-stage caches under `output/<run>/cache/` make crash-resume automatic — re-run to continue.

## Results

**ICML 2025 SeePhys Challenge** — 🥇 1st Place.

**SeePhys Pro 2026 (Codabench 16010, public testmini)** — current best:

| #  | Submission              | Overall    | L1    | L2    | L3    | L4    | L5    |
|---:|:------------------------|:----------:|:-----:|:-----:|:-----:|:-----:|:-----:|
|  1 | gemini baseline         | 0.7651     | 0.770 | 0.810 | 0.755 | 0.700 | 0.933 |
|  4 | + L4 verbatim caption   | 0.7747     | 0.765 | 0.810 | 0.760 | 0.740 | 0.933 |
|  8 | **+ L1 few-shot reason**| **0.7771** | 0.770 | 0.800 | 0.765 | 0.750 | 0.933 |

Full iteration log: [`seephys_pro_codabench/output/submissions/README.md`](seephys_pro_codabench/output/submissions/README.md).

## Layout

```
scireasoner/              Python package (CLI + MCP server, thin shell)
plugins/claude-code/      Claude Code one-click install
plugins/codex/            Codex one-click install
seephys_pro_codabench/    Active 2026 competition workspace (don't touch)
caption.py / answer.py    Original 2025 single-script implementation
```

The `scireasoner/` package imports stages directly from `seephys_pro_codabench/scripts/run_v2.py` without copying — so any improvement we push during the live competition flows to all downstream users on the next `git pull`.

## Citation

```bibtex
@article{liang2025multimodal,
  title  = {Multimodal Reasoning for Science: Technical Report and 1st Place
            Solution to the ICML 2025 SeePhys Challenge},
  author = {Liang, Hao and Wu, Ruitao and Zeng, Bohan and Niu, Junbo
            and Zhang, Wentao and Dong, Bin},
  journal= {arXiv preprint arXiv:2509.06079},
  year   = {2025}
}
```

## License

GPL-3.0. See [LICENSE](LICENSE). Thanks to the [ICML 2025 AI for Math Workshop](https://sites.google.com/view/ai4mathworkshopicml2025) organizers and Codabench / AWS for hosting.
