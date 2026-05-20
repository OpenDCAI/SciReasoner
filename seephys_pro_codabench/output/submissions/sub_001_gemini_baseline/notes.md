# Submission 1 — Gemini-3.1-Pro baseline (no audit)

- **Submitted**: 2026-05-19 16:06
- **Codabench ID**: 740536
- **Overall score**: **0.7651**   (= 635/830 correct)
- **Per level**: L1 0.770, L2 0.810, L3 0.755, L4 0.700, L5 0.933

## Pipeline

| Stage | Model | Notes |
|---|---|---|
| caption | gemini-3.1-pro-preview | Structured caption template; skipped for L1 + adaptive routing for 7 physics domains |
| reason  | gemini-3.1-pro-preview | k_samples=1, temp=0 |
| critic  | gemini-3.1-pro-preview | Verifies + may rewrite |

- max_tokens: 65536 (auto-escalate on finish_reason=length)
- workers: 50

## Cost
~$1500 for the full 830-question pipeline (Gemini-3.1-Pro is thinking-heavy).

## Scoring diagnostics
- judge: deepseek/deepseek-v4-pro (semantic, answer-only mode)
- 699/830 deterministically scored (598 correct), 131 sent to LLM judge
- 0 invalid, 0 missing
