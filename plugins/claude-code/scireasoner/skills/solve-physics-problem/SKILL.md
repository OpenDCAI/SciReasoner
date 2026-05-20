---
name: solve-physics-problem
description: Solve a physics problem (text + optional figure) using the SciReasoner caption→reason→critic pipeline. Trigger when the user asks to solve, verify, or critique a physics problem that has a diagram, plot, circuit, or other figure.
---

# Solve Physics Problem with SciReasoner

You have access to the SciReasoner pipeline via three MCP tools:

- **`scireasoner_solve`** — end-to-end (caption → reason → critic). Use this for normal solve requests.
- **`scireasoner_caption`** — caption stage only (figure → structured text). Use when the user wants the figure described, not solved.
- **`scireasoner_reason`** — reason stage only. Use when the user already provides a caption and only wants the derivation.

## When to use

Trigger this skill when the user:
- Provides a physics problem, especially one with a figure (image attached, file path mentioned, or screenshot pasted).
- Asks to "solve", "verify", "explain", "find the answer", or "critique" a physics problem.
- Posts an image of a physics question and asks for the answer.

## How to drive the tools

### Standard flow

For a typical request "solve this physics problem [image attached]":

```
scireasoner_solve(
    problem="<the user's problem text, verbatim if given; empty string if it's all in the image>",
    image_path="<absolute path to the figure>",
)
```

The tool returns `{answer, reasoning, caption}`. Present the **answer** first, then the **reasoning**, and optionally the **caption** if the user asked about the figure specifically.

### Variants

- **Text-only problem**: omit `image_path`. The pipeline will skip captioning automatically.
- **Higher accuracy at higher cost**: pass `k_samples=3` to enable self-consistency voting on the reason stage. Use sparingly — each unit increase triples the reason cost.
- **Quick draft**: pass `use_critic=False` to skip the critic+refine pass. Halves cost, slightly less reliable.
- **Caption only**: when the user just wants the figure described, call `scireasoner_caption` instead of `scireasoner_solve`.

## Output convention

Format your reply to the user as:

```
**Answer**: <final answer>

**Reasoning**:
<full chain of reasoning>

(optional, if a figure was provided)
**Figure description**:
<the structured caption>
```

Always preserve LaTeX as written by the model — wrap inline math in `\(...\)` and display math in `$$...$$` only if the user is in a Markdown-rendering environment.

## Notes for Claude

- The pipeline is opinionated about format: it produces `<reasoning>...</reasoning><answer>...</answer>`, but the MCP wrapper extracts those for you. Just present the fields directly.
- For multiple-choice problems, the answer will be a single letter or letter combination (e.g., `BD`).
- Numerical answers usually include LaTeX-style units (`\sqrt{35}\,\mathrm{m/s}`).
- If the user objects to an answer, run `scireasoner_solve` again with `k_samples=3` for a self-consistency vote, OR ask them to clarify what they think went wrong.
