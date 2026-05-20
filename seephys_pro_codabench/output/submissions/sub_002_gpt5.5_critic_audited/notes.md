# Submission 2 — GPT-5.5 critic + audit (REGRESSION ❌)

- **Submitted**: 2026-05-19 17:59
- **Overall score**: **0.7012**   (= 582/830 correct, **−53 questions vs sub_001**)
- **Per level**: L1 0.725, L2 0.715, L3 0.700, L4 0.635, L5 0.900
- **Per-level deltas vs sub_001**:
  - L1: −0.045 (−9 questions)
  - L2: −0.095 (−19 questions)  ← worst hit
  - L3: −0.055 (−11 questions)
  - L4: −0.065 (−13 questions)
  - L5: −0.033 (−1 question)

## Pipeline change vs Sub 1
- Replaced critic with **gpt-5.5** on cheap proxy (cache for caption + reason kept from sub_001)
- 48-fix audit pass (more fixes because gpt-5.5 was more verbose)

## Scoring diagnostics
- judge: deepseek/deepseek-v4-pro (semantic, answer-only mode)
- 660/830 deterministically scored (549 correct), 170 sent to LLM judge
- 0 invalid, 0 missing
- Note: items_to_llm went up from 131 → 170 (more borderline/non-canonical answers)

## Why it regressed
gpt-5.5 critic changed answers in 153/830 (18.4%) of cases. Many changes:
- Hedge ("Cannot be determined", "No real angular velocity exists")
- Format drift ("1.85" → "1.85 m", "BD" → "B, C")
- Multichoice broadening/narrowing

Judge is **answer-only** — verbose answers and hedges are penalized.

## Lesson
Heterogeneous critic is NOT a free improvement. Different models have different priors
on "what is a clean answer", and the judge punishes drift. Net delta was −53 questions
out of 153 changed (~34% regression rate among changes vs ~6% improvement rate, per
gpt-5.4 juror referee analysis).

## Files
- `submission.zip` — what we uploaded
- `prediction.csv` — same as inside submission.zip
- `prediction_pre_audit.csv` — gpt-5.5 critic output before audit was applied
- `prediction_result.zip` — Codabench echoed our submission back
- `scoring_result.zip` — Codabench scores.json + diagnostics.json
