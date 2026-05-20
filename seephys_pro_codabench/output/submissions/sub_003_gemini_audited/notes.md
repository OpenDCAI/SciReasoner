# Submission 3 — Gemini critic + audit (rollback, currently #1)

- **Submitted**: 2026-05-19 18:04
- **Codabench ID**: 740739
- **Overall score**: **0.7663**   (= 636/830 correct, **+1 question vs sub_001**)
- **Per level**: L1 0.770, L2 0.800, L3 0.765, L4 0.705, L5 0.933
- **Per-level deltas vs sub_001**:
  - L1: 0 (no change)
  - L2: −0.010 (−2 questions)
  - L3: +0.010 (+2 questions)
  - L4: +0.005 (+1 question)
  - L5: 0 (no change)

## Pipeline
Same as Sub 1 (Gemini caption + reason + critic) PLUS 6 deterministic audit fixes:

| # | Question | Before | After | Reason |
|---|---|---|---|---|
| 1 | solve150_testmini_000011 (L5) | `d` | `D` | uppercase multichoice |
| 2 | solve150_testmini_000012 (L5) | `b` | `B` | uppercase multichoice |
| 3 | solve150_testmini_000014 (L5) | `b` | `B` | uppercase multichoice |
| 4 | level4_testmini_000027 | leaked-reasoning | `BD` | critic-truncation → reason fallback |
| 5 | level4_testmini_000044 | leaked-LaTeX | `\(\frac{4}{3}U\)` | same |
| 6 | level4_testmini_000155 | leaked-reasoning | `385` | same |

## Scoring diagnostics
- judge: deepseek/deepseek-v4-pro (semantic, answer-only mode)
- 700/830 deterministically scored (599 correct), 130 sent to LLM judge
- 0 invalid, 0 missing
- Note: items_to_llm went DOWN from 131 → 130 (audit cleaned 1 borderline format)

## Real signal vs noise
- **L4 +1 question**: real (truncation fallback recovered a correct answer)
- **L3 +2 questions / L2 −2 questions**: judge noise — audit didn't touch any L2/L3 question
  - Implication: deepseek-v4-pro semantic judge has ~±1-2 question noise per level (~±0.005-0.010 per level on 200-question sets)
- L5 uppercase changes: net 0 — judge appears case-insensitive on multichoice

## Net real improvement: +1 question (audit recovered one truncated L4)

## Currently leaderboard #1 (slightly above ctree4113's 0.7637)

## Files
- `submission.zip` — uploaded
- `prediction.csv` — same as inside submission.zip
- `prediction_result.zip` — Codabench echo
- `scoring_result.zip` — scores.json + diagnostics.json
